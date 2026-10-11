# Handles approve, reject, and ignore actions with database transactions and locking.

from django.db import transaction
from django.http import Http404

from ..exceptions import Conflict
from ..models import BankTransaction, LineItem, Organization, ReconciliationMatch

Status = BankTransaction.Status
MatchStatus = ReconciliationMatch.Status


def _get_match_transaction_id(organization: Organization, match_id: int) -> int:
    tx_id = (
        ReconciliationMatch.objects.filter(organization=organization, pk=match_id)
        .values_list("transaction_id", flat=True)
        .first()
    )
    if tx_id is None:
        raise Http404("Match not found.")
    return tx_id


def _lock_transaction(organization: Organization, transaction_id: int) -> BankTransaction:
    tx = BankTransaction.objects.select_for_update().filter(organization=organization, pk=transaction_id).first()
    if tx is None:
        raise Http404("Transaction not found.")
    return tx


def _lock_matches(tx: BankTransaction) -> list[ReconciliationMatch]:
    return list(ReconciliationMatch.objects.select_for_update().filter(transaction=tx).order_by("id"))


def approve_match(*, organization: Organization, match_id: int) -> ReconciliationMatch:
    with transaction.atomic():
        tx = _lock_transaction(organization, _get_match_transaction_id(organization, match_id))
        line_item_id = (
            ReconciliationMatch.objects.filter(pk=match_id, transaction=tx).values_list("line_item_id", flat=True).get()
        )
        line_item = LineItem.objects.select_for_update().get(organization=organization, pk=line_item_id)
        matches = _lock_matches(tx)
        match = next(m for m in matches if m.pk == match_id)

        if match.status != MatchStatus.PROPOSED:
            raise Conflict(f"Match is already {match.status}.", "match_not_proposed")
        if tx.status == Status.RECONCILED:
            raise Conflict("Transaction is already reconciled.", "transaction_reconciled")
        if tx.status == Status.IGNORED or tx.type != BankTransaction.Type.CREDIT:
            raise Conflict("Only unreconciled credit transactions can be approved.", "transaction_not_approvable")

        remaining = line_item.amount_called - line_item.amount_funded
        if tx.amount > remaining:
            raise Conflict(
                f"Payment of {tx.amount:,.2f} exceeds the {remaining:,.2f} remaining on "
                f"{line_item.expected_wire_reference}.",
                "exceeds_remaining",
            )

        line_item.amount_funded += tx.amount
        line_item.status = LineItem.status_for(line_item.amount_funded, line_item.amount_called)
        line_item.save(update_fields=["amount_funded", "status"])

        for other in matches:
            if other.pk != match.pk and other.status == MatchStatus.PROPOSED:
                other.status = MatchStatus.REJECTED
                other.save(update_fields=["status"])
        match.status = MatchStatus.APPROVED
        match.save(update_fields=["status"])

        tx.status = Status.RECONCILED
        tx.review_reason = None
        tx.save(update_fields=["status", "review_reason"])
        return match


def reject_match(*, organization: Organization, match_id: int) -> ReconciliationMatch:
    with transaction.atomic():
        tx = _lock_transaction(organization, _get_match_transaction_id(organization, match_id))
        matches = _lock_matches(tx)
        match = next(m for m in matches if m.pk == match_id)

        if match.status != MatchStatus.PROPOSED:
            raise Conflict(f"Match is already {match.status}.", "match_not_proposed")
        if tx.status in (Status.RECONCILED, Status.IGNORED):
            raise Conflict(f"Transaction is already {tx.status}.", "transaction_closed")

        match.status = MatchStatus.REJECTED
        match.save(update_fields=["status"])

        if not any(m.status == MatchStatus.PROPOSED for m in matches):
            tx.status = Status.NEEDS_REVIEW
            tx.review_reason = "All proposed matches were rejected; manual review required."
            tx.save(update_fields=["status", "review_reason"])
        return match


def ignore_transaction(*, organization: Organization, transaction_id: int) -> BankTransaction:
    with transaction.atomic():
        tx = _lock_transaction(organization, transaction_id)
        matches = _lock_matches(tx)

        if tx.status == Status.RECONCILED:
            raise Conflict("A reconciled transaction cannot be ignored.", "transaction_reconciled")
        if tx.status == Status.IGNORED:
            raise Conflict("Transaction is already ignored.", "transaction_ignored")
        if tx.type != BankTransaction.Type.CREDIT:
            raise Conflict("Only credit transactions can be ignored.", "transaction_not_credit")

        for match in matches:
            if match.status == MatchStatus.PROPOSED:
                match.status = MatchStatus.REJECTED
                match.save(update_fields=["status"])
        tx.status = Status.IGNORED
        tx.review_reason = "Ignored by a reviewer."
        tx.save(update_fields=["status", "review_reason"])
        return tx
