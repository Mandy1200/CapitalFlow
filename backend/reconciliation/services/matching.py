# Matching engine for capital call reconciliation
# Normalizes references/names and matches bank credits against eligible line items.

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from functools import lru_cache

SUGGESTED = "suggested"
NEEDS_REVIEW = "needs_review"

LEGAL_SUFFIXES = frozenset({"LLC", "LP", "LTD", "INC"})

_NON_ALNUM = re.compile(r"[^A-Z0-9]+")


@lru_cache(maxsize=4096)
def normalize_reference(value: str) -> str:
    """Uppercase and keep only letters and digits: ``cc-1003`` -> ``CC1003``."""
    return _NON_ALNUM.sub("", (value or "").upper())


@lru_cache(maxsize=4096)
def normalize_text(value: str) -> str:
    """Uppercase, turn every non-alphanumeric run into one space, trim."""
    return _NON_ALNUM.sub(" ", (value or "").upper()).strip()


@lru_cache(maxsize=4096)
def normalize_name(value: str) -> str:
    """Normalize an investor name and drop one trailing legal suffix.

    ``Meridian Partners LP`` -> ``MERIDIAN PARTNERS``; ``TRUST`` is kept.
    """
    # TODO: In production, consider phonetic matching (e.g. Soundex) for LP typos
    words = normalize_text(value).split(" ")
    if len(words) > 1 and words[-1] in LEGAL_SUFFIXES:
        words = words[:-1]
    return " ".join(word for word in words if word)


def contains_whole_words(haystack: str, needle: str) -> bool:
    # Check whole-word containment on space-separated normalized text
    if not needle:
        return False
    return f" {needle} " in f" {haystack} "


def format_money(amount: Decimal) -> str:
    return f"{amount:,.2f}"


@dataclass(frozen=True)
class CandidateLineItem:
    id: int
    investor_name: str
    expected_wire_reference: str
    call_number: int
    call_date: date
    remaining: Decimal


@dataclass(frozen=True)
class ProposedMatch:
    line_item_id: int
    reason: str


@dataclass(frozen=True)
class MatchOutcome:
    status: str
    review_reason: str | None
    proposals: tuple[ProposedMatch, ...] = field(default_factory=tuple)


def _ineligibility(item: CandidateLineItem, transaction_date: date) -> str | None:
    if item.remaining <= 0:
        return "the line item is already fully funded"
    if item.call_date > transaction_date:
        return (
            f"capital call #{item.call_number} is dated {item.call_date.isoformat()}, "
            f"after the transaction date {transaction_date.isoformat()}"
        )
    return None


def _reference_found(item: CandidateLineItem, description_ref: str, bank_ref: str) -> bool:
    expected = normalize_reference(item.expected_wire_reference)
    return bool(expected) and (expected in description_ref or expected in bank_ref)


def _reference_reason(item: CandidateLineItem, amount: Decimal) -> str:
    ref = item.expected_wire_reference
    if amount == item.remaining:
        return f"Reference {ref} found; amount equals remaining {format_money(item.remaining)}."
    if amount < item.remaining:
        return (
            f"Reference {ref} found; partial payment of {format_money(amount)} "
            f"against {format_money(item.remaining)} remaining."
        )
    return (
        f"Reference {ref} found; amount {format_money(amount)} exceeds the "
        f"{format_money(item.remaining)} remaining, so approval would be refused."
    )


def _refs(items) -> str:
    return ", ".join(item.expected_wire_reference for item in items)


def match_transaction(
    *,
    transaction_date: date,
    description: str,
    amount: Decimal,
    bank_reference: str,
    line_items: list[CandidateLineItem],
) -> MatchOutcome:
    """Propose matches for one credit transaction. ``amount`` must be positive."""
    if not isinstance(amount, Decimal):
        raise TypeError("amount must be a Decimal")
    if amount <= 0:
        raise ValueError("Only credits with a positive amount can be matched.")

    eligible = [item for item in line_items if _ineligibility(item, transaction_date) is None]
    description_ref = normalize_reference(description)
    bank_ref = normalize_reference(bank_reference)

    # Step 2: reference matching.
    reference_hits = [item for item in eligible if _reference_found(item, description_ref, bank_ref)]
    if len(reference_hits) == 1:
        item = reference_hits[0]
        if amount <= item.remaining:
            return MatchOutcome(SUGGESTED, None, (ProposedMatch(item.id, _reference_reason(item, amount)),))
        return MatchOutcome(
            NEEDS_REVIEW,
            f"Overpayment: transaction amount {format_money(amount)} exceeds the "
            f"{format_money(item.remaining)} remaining balance on {item.expected_wire_reference}.",
        )
    if len(reference_hits) > 1:
        return MatchOutcome(
            NEEDS_REVIEW,
            f"Multiple eligible reference matches found ({_refs(reference_hits)}); manual review required.",
            tuple(ProposedMatch(item.id, _reference_reason(item, amount)) for item in reference_hits),
        )

    # Step 3: investor name plus exact remaining amount.
    normalized_description = normalize_text(description)
    name_hits = [
        item
        for item in eligible
        if amount == item.remaining
        and contains_whole_words(normalized_description, normalize_name(item.investor_name))
    ]
    proposals = tuple(
        ProposedMatch(
            item.id,
            f"Investor name {normalize_name(item.investor_name)} found in description; amount equals "
            f"remaining {format_money(item.remaining)} on {item.expected_wire_reference}.",
        )
        for item in name_hits
    )
    if len(name_hits) == 1:
        return MatchOutcome(SUGGESTED, None, proposals)
    if len(name_hits) > 1:
        return MatchOutcome(
            NEEDS_REVIEW,
            f"Multiple eligible name and exact-amount matches found ({_refs(name_hits)}); manual review required.",
            proposals,
        )

    reason = "No eligible reference, name and exact-amount match found."
    # Explain references that were present but could not be used, so a
    # reviewer is not left guessing why an obvious-looking wire was not matched.
    blocked = [
        f"Reference {item.expected_wire_reference} found but not eligible: {_ineligibility(item, transaction_date)}."
        for item in line_items
        if item not in eligible and _reference_found(item, description_ref, bank_ref)
    ]
    if blocked:
        reason = " ".join([reason, *blocked])
    return MatchOutcome(NEEDS_REVIEW, reason)
