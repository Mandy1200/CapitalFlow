"""Overpayment/unmatched outcomes, approval safety, rejection and ignore."""

from decimal import Decimal

from rest_framework.test import APITestCase

from reconciliation.models import BankTransaction, LineItem, ReconciliationMatch

from .helpers import csv_text, line_item, post, proposed, seed, tx, upload


class OverpaymentAndUnmatchedTests(APITestCase):
    """Test 6."""

    def setUp(self):
        seed()

    def test_overpayment_and_unknown_wire(self):
        upload(
            self.client,
            csv_text(
                "2026-04-15,WIRE INCOMING PATEL FAMILY TRUST CC-1003,13000.00,credit,OVER",
                "2026-04-09,UNKNOWN INCOMING WIRE,9999.99,credit,UNKNOWN",
            ),
        )
        over = tx("OVER")
        self.assertEqual(over.status, "needs_review")
        self.assertEqual(over.matches.count(), 0)
        self.assertEqual(
            over.review_reason,
            "Overpayment: transaction amount 13,000.00 exceeds the 12,500.00 remaining balance on CC-1003.",
        )
        unknown = tx("UNKNOWN")
        self.assertEqual(unknown.status, "needs_review")
        self.assertEqual(unknown.matches.count(), 0)
        self.assertEqual(unknown.review_reason, "No eligible reference, name and exact-amount match found.")


class ApprovalTests(APITestCase):
    """Test 7 (sequential part; see test_concurrency for parallel requests)."""

    def setUp(self):
        seed()
        upload(
            self.client,
            csv_text(
                "2026-04-03,WIRE INCOMING RAHUL SHAH TRUST REF CC-1002,25000.00,credit,FULL",
                "2026-04-04,ACH CREDIT HALLER CAPITAL LLC CC-1001,20000.00,credit,PART1",
                "2026-04-14,ACH CREDIT HALLER CAPITAL cc1001,7500.00,credit,PART2",
                "2026-04-15,HALLER CAPITAL CC-1001 TOP UP,7500.00,credit,PART3",
                "2026-04-11,WIRE INCOMING OAKRIDGE HOLDINGS LLC,15000.00,credit,AMBIG",
            ),
        )

    def approve(self, reference, index=0, org="northwind"):
        return post(self.client, f"/api/matches/{proposed(reference)[index].pk}/approve/", org)

    def test_approve_updates_funding_and_statuses(self):
        match = proposed("FULL")[0]
        response = post(self.client, f"/api/matches/{match.pk}/approve/")
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["transaction"]["status"], "reconciled")
        self.assertEqual(body["line_item"]["status"], "funded")
        self.assertEqual(body["line_item"]["remaining_amount"], "0.00")

        item = line_item("CC-1002")
        self.assertEqual((item.amount_funded, item.status), (Decimal("25000.00"), "funded"))
        match.refresh_from_db()
        self.assertEqual(match.status, "approved")
        self.assertEqual(tx("FULL").status, "reconciled")

        # The same approval again: 409 and no extra funding.
        again = post(self.client, f"/api/matches/{match.pk}/approve/")
        self.assertEqual(again.status_code, 409)
        self.assertEqual(again.json()["error"]["code"], "match_not_proposed")
        self.assertEqual(line_item("CC-1002").amount_funded, Decimal("25000.00"))

    def test_multiple_partial_payments_then_overfunding_is_refused(self):
        # PART3 was proposed at import time against the then-remaining 27,500.00.
        part3 = proposed("PART3")[0]
        self.assertEqual(self.approve("PART1").status_code, 200)
        item = line_item("CC-1001")
        self.assertEqual((item.amount_funded, item.status), (Decimal("20000.00"), "partially_funded"))

        self.assertEqual(self.approve("PART2").status_code, 200)
        item = line_item("CC-1001")
        self.assertEqual((item.amount_funded, item.status), (Decimal("27500.00"), "funded"))

        response = post(self.client, f"/api/matches/{part3.pk}/approve/")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "exceeds_remaining")
        part3.refresh_from_db()
        self.assertEqual(part3.status, "proposed")
        self.assertEqual(tx("PART3").status, "suggested")
        self.assertEqual(line_item("CC-1001").amount_funded, Decimal("27500.00"))

    def test_ambiguous_transaction_approves_only_chosen_candidate(self):
        first, second = proposed("AMBIG")
        self.assertEqual(tx("AMBIG").status, "needs_review")
        response = post(self.client, f"/api/matches/{second.pk}/approve/")
        self.assertEqual(response.status_code, 200)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.status, second.status), ("rejected", "approved"))
        self.assertEqual(line_item("CC-1006").status, "funded")
        self.assertEqual(line_item("CC-1005").amount_funded, Decimal("0.00"))
        # The rejected sibling can no longer fund anything.
        self.assertEqual(post(self.client, f"/api/matches/{first.pk}/approve/").status_code, 409)

    def test_one_transaction_cannot_fund_two_line_items_even_with_forged_match(self):
        self.assertEqual(self.approve("PART1").status_code, 200)
        reconciled = tx("PART1")
        forged = ReconciliationMatch.objects.create(
            organization=reconciled.organization,
            transaction=reconciled,
            line_item=line_item("CC-1004"),
            status="proposed",
            reason="forged",
        )
        response = post(self.client, f"/api/matches/{forged.pk}/approve/")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "transaction_reconciled")
        self.assertEqual(line_item("CC-1004").amount_funded, Decimal("0.00"))

    def test_unknown_match_returns_404(self):
        self.assertEqual(post(self.client, "/api/matches/999999/approve/").status_code, 404)


class RejectAndIgnoreTests(APITestCase):
    def setUp(self):
        seed()
        upload(
            self.client,
            csv_text(
                "2026-04-03,WIRE INCOMING RAHUL SHAH TRUST REF CC-1002,25000.00,credit,FULL",
                "2026-04-11,WIRE INCOMING OAKRIDGE HOLDINGS LLC,15000.00,credit,AMBIG",
                "2026-04-09,UNKNOWN INCOMING WIRE,9999.99,credit,UNKNOWN",
                "2026-04-05,BANK FEE WIRE PROCESSING,-25.00,debit,FEE",
            ),
        )

    def test_reject_only_match_moves_transaction_to_review(self):
        (match,) = proposed("FULL")
        response = post(self.client, f"/api/matches/{match.pk}/reject/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["transaction"]["status"], "needs_review")
        self.assertIn("rejected", tx("FULL").review_reason)
        self.assertEqual(line_item("CC-1002").amount_funded, Decimal("0.00"))
        # No silent re-matching: nothing new was proposed.
        self.assertEqual(proposed("FULL"), [])
        self.assertEqual(post(self.client, f"/api/matches/{match.pk}/reject/").status_code, 409)
        self.assertEqual(post(self.client, f"/api/matches/{match.pk}/approve/").status_code, 409)

    def test_reject_one_of_several_keeps_the_rest(self):
        first, second = proposed("AMBIG")
        post(self.client, f"/api/matches/{first.pk}/reject/")
        self.assertEqual(proposed("AMBIG"), [second])
        self.assertEqual(tx("AMBIG").status, "needs_review")

    def test_ignore_suggested_and_needs_review(self):
        response = post(self.client, f"/api/transactions/{tx('FULL').pk}/ignore/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ignored")
        self.assertEqual(proposed("FULL"), [])
        self.assertEqual(ReconciliationMatch.objects.get(transaction=tx("FULL")).status, "rejected")
        self.assertEqual(post(self.client, f"/api/transactions/{tx('UNKNOWN').pk}/ignore/").status_code, 200)
        self.assertEqual(line_item("CC-1002").amount_funded, Decimal("0.00"))

    def test_ignore_conflicts(self):
        # Already ignored, debit, reconciled, approve after ignore.
        fee = tx("FEE")
        self.assertEqual(post(self.client, f"/api/transactions/{fee.pk}/ignore/").status_code, 409)

        (match,) = proposed("FULL")
        post(self.client, f"/api/matches/{match.pk}/approve/")
        response = post(self.client, f"/api/transactions/{tx('FULL').pk}/ignore/")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "transaction_reconciled")
        self.assertEqual(tx("FULL").status, "reconciled")
        self.assertEqual(line_item("CC-1002").amount_funded, Decimal("25000.00"))

        ambig = tx("AMBIG")
        candidate = proposed("AMBIG")[0]
        post(self.client, f"/api/transactions/{ambig.pk}/ignore/")
        self.assertEqual(post(self.client, f"/api/matches/{candidate.pk}/approve/").status_code, 409)
        self.assertEqual(LineItem.objects.get(expected_wire_reference="CC-1005").amount_funded, Decimal("0.00"))


class DatabaseConstraintTests(APITestCase):
    def setUp(self):
        seed()

    def test_line_item_cannot_be_overfunded_at_database_level(self):
        from django.db import IntegrityError, transaction

        item = line_item("CC-1003")
        item.amount_funded = item.amount_called + Decimal("0.01")
        with self.assertRaises(IntegrityError), transaction.atomic():
            item.save()

    def test_transaction_sign_must_match_type(self):
        from django.db import IntegrityError, transaction

        org = line_item("CC-1003").organization
        with self.assertRaises(IntegrityError), transaction.atomic():
            BankTransaction.objects.create(
                organization=org,
                transaction_date="2026-04-01",
                description="x",
                amount=Decimal("-5.00"),
                type="credit",
                bank_reference="SIGN",
                status="needs_review",
            )
