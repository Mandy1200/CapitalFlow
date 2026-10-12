"""Unit tests for the pure matching engine (no database)."""

from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase

from reconciliation.services.matching import (
    NEEDS_REVIEW,
    SUGGESTED,
    CandidateLineItem,
    contains_whole_words,
    match_transaction,
    normalize_name,
    normalize_reference,
)

CALL_1 = date(2026, 3, 25)
CALL_2 = date(2026, 4, 1)


def item(id, name, ref, remaining, call_date=CALL_1, call_number=1):
    return CandidateLineItem(id, name, ref, call_number, call_date, Decimal(remaining))


NORTHWIND = [
    item(1, "Haller Capital LLC", "CC-1001", "27500.00"),
    item(2, "Rahul Shah Trust", "CC-1002", "25000.00"),
    item(3, "Patel Family Trust", "CC-1003", "12500.00"),
    item(4, "Meridian Partners LP", "CC-1004", "15000.00"),
    item(5, "Oakridge Holdings LLC", "CC-1005", "15000.00"),
    item(6, "Oakridge Holdings LLC", "CC-1006", "15000.00", CALL_2, 2),
]


def run(description, amount, when=date(2026, 4, 12), reference="BANKREF1", items=NORTHWIND):
    return match_transaction(
        transaction_date=when,
        description=description,
        amount=Decimal(amount),
        bank_reference=reference,
        line_items=items,
    )


class NormalizationTests(SimpleTestCase):
    def test_reference_normalization(self):
        self.assertEqual(normalize_reference("cc-1003"), "CC1003")
        self.assertEqual(normalize_reference("CC 1003"), "CC1003")
        self.assertEqual(normalize_reference(" cc_10/03 "), "CC1003")

    def test_name_normalization_strips_one_trailing_legal_suffix(self):
        self.assertEqual(normalize_name("Meridian Partners LP"), "MERIDIAN PARTNERS")
        self.assertEqual(normalize_name("Haller Capital, LLC."), "HALLER CAPITAL")
        self.assertEqual(normalize_name("Acme Ltd"), "ACME")
        self.assertEqual(normalize_name("Acme  Inc"), "ACME")
        self.assertEqual(normalize_name("Patel Family Trust"), "PATEL FAMILY TRUST")
        # Only a trailing suffix is removed, and a bare suffix is not emptied.
        self.assertEqual(normalize_name("LLC Holdings"), "LLC HOLDINGS")
        self.assertEqual(normalize_name("LP"), "LP")

    def test_whole_word_matching(self):
        self.assertTrue(contains_whole_words("WIRE HALLER CAPITAL CC 1001", "HALLER CAPITAL"))
        self.assertFalse(contains_whole_words("WIRE SHALLER CAPITAL", "HALLER CAPITAL"))
        self.assertFalse(contains_whole_words("WIRE HALLER CAPITALS", "HALLER CAPITAL"))


class ReferenceMatchingTests(SimpleTestCase):
    def test_reference_with_punctuation_and_exact_amount(self):
        outcome = run("WIRE INCOMING RAHUL SHAH TRUST REF CC-1002", "25000.00")
        self.assertEqual(outcome.status, SUGGESTED)
        self.assertEqual([p.line_item_id for p in outcome.proposals], [2])
        self.assertEqual(outcome.proposals[0].reason, "Reference CC-1002 found; amount equals remaining 25,000.00.")

    def test_lowercase_reference_without_dash_is_a_partial_payment(self):
        outcome = run("ACH CREDIT HALLER CAPITAL cc1001", "7500.00")
        self.assertEqual(outcome.status, SUGGESTED)
        self.assertEqual([p.line_item_id for p in outcome.proposals], [1])
        self.assertEqual(
            outcome.proposals[0].reason,
            "Reference CC-1001 found; partial payment of 7,500.00 against 27,500.00 remaining.",
        )

    def test_reference_in_bank_reference_field(self):
        outcome = run("INCOMING WIRE", "100.00", reference="cc-1003/x")
        self.assertEqual([p.line_item_id for p in outcome.proposals], [3])

    def test_overpayment_needs_review_without_match(self):
        outcome = run("WIRE INCOMING PATEL FAMILY TRUST CC-1003", "13000.00")
        self.assertEqual(outcome.status, NEEDS_REVIEW)
        self.assertEqual(outcome.proposals, ())
        self.assertIn("Overpayment", outcome.review_reason)
        self.assertIn("12,500.00", outcome.review_reason)

    def test_multiple_reference_matches_need_review_with_all_candidates(self):
        outcome = run("WIRE FOR CC-1001 AND CC-1002", "5000.00")
        self.assertEqual(outcome.status, NEEDS_REVIEW)
        self.assertEqual([p.line_item_id for p in outcome.proposals], [1, 2])
        self.assertIn("Multiple eligible reference matches", outcome.review_reason)

    def test_reference_match_skips_name_matching(self):
        # The description also names Patel with the exact Patel amount, but the
        # reference to CC-1001 wins and name matching never runs.
        outcome = run("PATEL FAMILY TRUST CC-1001", "12500.00")
        self.assertEqual([p.line_item_id for p in outcome.proposals], [1])

    def test_future_capital_call_is_not_eligible(self):
        outcome = run("WIRE INCOMING OAKRIDGE HOLDINGS LLC REF CC-1006", "15000.00", when=date(2026, 3, 20))
        self.assertEqual(outcome.status, NEEDS_REVIEW)
        self.assertEqual(outcome.proposals, ())
        self.assertIn("No eligible reference, name and exact-amount match found.", outcome.review_reason)
        self.assertIn("CC-1006 found but not eligible", outcome.review_reason)

    def test_capital_call_dated_same_day_is_eligible(self):
        outcome = run("CC-1006", "15000.00", when=CALL_2)
        self.assertEqual([p.line_item_id for p in outcome.proposals], [6])

    def test_fully_funded_line_item_is_not_eligible(self):
        items = [item(1, "Haller Capital LLC", "CC-1001", "0.00")]
        outcome = run("HALLER CAPITAL CC-1001", "100.00", items=items)
        self.assertEqual(outcome.status, NEEDS_REVIEW)
        self.assertIn("fully funded", outcome.review_reason)


class NameAndAmountMatchingTests(SimpleTestCase):
    def test_name_and_exact_amount(self):
        outcome = run("WIRE INCOMING PATEL FAMILY TRUST", "12500.00")
        self.assertEqual(outcome.status, SUGGESTED)
        self.assertEqual([p.line_item_id for p in outcome.proposals], [3])
        self.assertIn("PATEL FAMILY TRUST", outcome.proposals[0].reason)

    def test_legal_suffix_is_ignored_and_case_and_spacing_normalized(self):
        outcome = run("  wire incoming meridian partners  ", "15000.00")
        self.assertEqual(outcome.status, SUGGESTED)
        self.assertEqual([p.line_item_id for p in outcome.proposals], [4])

    def test_name_requires_exact_remaining_amount(self):
        outcome = run("WIRE INCOMING PATEL FAMILY TRUST", "12499.99")
        self.assertEqual(outcome.status, NEEDS_REVIEW)
        self.assertEqual(outcome.proposals, ())

    def test_multiple_name_candidates_need_review(self):
        outcome = run("WIRE INCOMING OAKRIDGE HOLDINGS LLC", "15000.00")
        self.assertEqual(outcome.status, NEEDS_REVIEW)
        self.assertEqual([p.line_item_id for p in outcome.proposals], [5, 6])
        self.assertIn("Multiple eligible name and exact-amount matches", outcome.review_reason)

    def test_ineligible_candidate_reduces_ambiguity(self):
        # Before Call #2's date only CC-1005 is eligible.
        outcome = run("WIRE INCOMING OAKRIDGE HOLDINGS LLC", "15000.00", when=date(2026, 3, 30))
        self.assertEqual(outcome.status, SUGGESTED)
        self.assertEqual([p.line_item_id for p in outcome.proposals], [5])

    def test_unknown_wire_needs_review(self):
        outcome = run("UNKNOWN INCOMING WIRE", "9999.99")
        self.assertEqual(outcome.status, NEEDS_REVIEW)
        self.assertEqual(outcome.proposals, ())
        self.assertEqual(outcome.review_reason, "No eligible reference, name and exact-amount match found.")


class GuardTests(SimpleTestCase):
    def test_rejects_floats_and_non_positive_amounts(self):
        with self.assertRaises(TypeError):
            match_transaction(
                transaction_date=CALL_1, description="x", amount=10.0, bank_reference="r", line_items=[]
            )
        with self.assertRaises(ValueError):
            run("x", "-1.00")
