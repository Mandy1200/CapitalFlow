"""CSV import: file validation, row validation, duplicates and import-time matching."""

from decimal import Decimal
from pathlib import Path

from unittest import skipUnless

from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from reconciliation.models import BankTransaction, ReconciliationMatch

from .helpers import csv_text, line_item, proposed, seed, tx, upload

# Repository root locally; mounted at /sample_bank_statement.csv in the Docker backend container.
SAMPLE_CSV = Path(__file__).resolve().parents[3] / "sample_bank_statement.csv"


class MissingColumnTests(APITestCase):
    """Test 1: a missing required column rejects the whole file."""

    def setUp(self):
        seed()

    def test_missing_column_returns_400_and_saves_nothing(self):
        text = csv_text(
            "2026-04-03,WIRE INCOMING RAHUL SHAH TRUST REF CC-1002,25000.00,FT1",
            header="date,description,amount,reference",
        )
        response = upload(self.client, text)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "invalid_csv")
        self.assertEqual(response.json()["error"]["details"]["missing_columns"], ["type"])
        self.assertEqual(BankTransaction.objects.count(), 0)

    def test_header_whitespace_case_and_column_order_are_tolerated(self):
        text = csv_text(
            "FT1,credit,100.00,WIRE,2026-04-03", header=" Reference , TYPE,amount ,description,date"
        )
        response = upload(self.client, text)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["imported_count"], 1)

    def test_missing_file_empty_file_and_non_utf8(self):
        self.assertEqual(self.client.post("/api/imports/", {}, HTTP_X_ORGANIZATION="northwind").status_code, 400)
        self.assertEqual(upload(self.client, "").status_code, 400)
        from django.core.files.uploadedfile import SimpleUploadedFile

        bad = SimpleUploadedFile("x.csv", b"date,description\xff\n", content_type="text/csv")
        response = self.client.post("/api/imports/", {"file": bad}, HTTP_X_ORGANIZATION="northwind")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(BankTransaction.objects.count(), 0)


class ParsingAndValidationTests(APITestCase):
    """Test 2: per-row validation; valid rows still import."""

    def setUp(self):
        seed()

    def test_row_validation(self):
        text = csv_text(
            '2026-04-03,  THOUSANDS  ,"25,000.00",credit,  REF-OK1  ',  # line 2: valid
            "2026-04-31,BAD DAY,100.00,credit,REF-2",  # 3: impossible date
            "04/05/2026,BAD FORMAT,100.00,credit,REF-3",  # 4: wrong format
            "2026-04-05,ZERO,0.00,credit,REF-4",  # 5: zero
            "2026-04-05,TEXT,abc,credit,REF-5",  # 6: not a number
            "2026-04-05,NEG CREDIT,-15000.00,credit,REF-6",  # 7: credit must be positive
            "2026-04-05,POS DEBIT,25.00,debit,REF-7",  # 8: debit must be negative
            "2026-04-05,UPPER,7500.00,CREDIT,REF-OK8",  # 9: valid, case-insensitive type
            "2026-04-05,FEE,-25,Debit,REF-OK9",  # 10: valid debit
            "2026-04-05,,100.00,credit,REF-10",  # 11: empty description
            "2026-04-05,NO REF,100.00,credit,",  # 12: empty reference
            "2026-04-05,BAD TYPE,100.00,transfer,REF-12",  # 13: unknown type
            "2026-04-05,BAD COMMAS,\"2,50.00\",credit,REF-13",  # 14: misplaced separator
            "2026-04-05,TOO PRECISE,10.001,credit,REF-14",  # 15: more than 2 decimals
        )
        response = upload(self.client, text)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["imported_count"], 3)
        self.assertEqual(body["error_count"], 11)
        self.assertEqual(body["imported_breakdown"]["credits"], 2)
        self.assertEqual(body["imported_breakdown"]["debits"], 1)
        errors = {e["line"]: e["message"] for e in body["errors"]}
        self.assertEqual(sorted(errors), [3, 4, 5, 6, 7, 8, 11, 12, 13, 14, 15])
        self.assertIn("not a real calendar date", errors[3])
        self.assertIn("expected YYYY-MM-DD", errors[4])
        self.assertIn("must not be zero", errors[5])
        self.assertIn("Invalid amount", errors[6])
        self.assertIn("Credit amount must be positive", errors[7])
        self.assertIn("Debit amount must be negative", errors[8])
        self.assertIn("Description is required", errors[11])
        self.assertIn("Reference is required", errors[12])
        self.assertIn("Invalid type", errors[13])

        thousands = tx("REF-OK1")
        thousands.refresh_from_db()
        self.assertIsInstance(thousands.amount, Decimal)
        self.assertEqual(thousands.amount, Decimal("25000.00"))
        self.assertEqual(thousands.description, "THOUSANDS")
        self.assertEqual(tx("REF-OK8").type, "credit")
        debit = tx("REF-OK9")
        self.assertEqual((debit.type, debit.status, debit.amount), ("debit", "ignored", Decimal("-25.00")))
        self.assertEqual(debit.matches.count(), 0)
        for amount in BankTransaction.objects.values_list("amount", flat=True):
            self.assertIsInstance(amount, Decimal)

    def test_line_numbers_are_physical_lines(self):
        text = 'date,description,amount,type,reference\n\n2026-04-03,"MULTI\nLINE",100.00,credit,R1\n2026-02-30,X,1,credit,R2\n'
        body = upload(self.client, text).json()
        self.assertEqual(body["imported_count"], 1)
        self.assertEqual(body["errors"], [{"line": 5, "message": "Invalid date '2026-02-30'; not a real calendar date."}])

    def test_short_rows_are_reported(self):
        body = upload(self.client, csv_text("2026-04-03,ONLY THREE,100.00")).json()
        self.assertEqual(body["errors"][0]["line"], 2)
        self.assertEqual(body["imported_count"], 0)


class DuplicateTests(APITestCase):
    """Test 3: duplicates within a file, across uploads, and across organizations."""

    def setUp(self):
        seed()

    def test_second_upload_reports_duplicate(self):
        text = csv_text("2026-04-03,WIRE INCOMING RAHUL SHAH TRUST REF CC-1002,25000.00,credit,FT20260403A")
        first = upload(self.client, text).json()
        self.assertEqual((first["imported_count"], first["duplicate_count"]), (1, 0))
        second = upload(self.client, text).json()
        self.assertEqual((second["imported_count"], second["duplicate_count"]), (0, 1))
        self.assertEqual(second["duplicates"][0]["message"], "Reference was already imported.")
        self.assertEqual(BankTransaction.objects.count(), 1)
        self.assertEqual(ReconciliationMatch.objects.count(), 1)

    def test_duplicate_inside_one_file(self):
        row = "2026-04-03,WIRE INCOMING RAHUL SHAH TRUST REF CC-1002,25000.00,credit,FT20260403A"
        body = upload(self.client, csv_text(row, "2026-04-04,OTHER,10.00,credit,FT2", row)).json()
        self.assertEqual((body["imported_count"], body["duplicate_count"]), (2, 1))
        self.assertEqual(body["duplicates"][0]["line"], 4)
        self.assertIn("line 2", body["duplicates"][0]["message"])

    def test_same_reference_in_different_organizations_is_not_a_duplicate(self):
        text = csv_text("2026-04-16,WIRE INCOMING CEDAR GROVE FUND CC-2001,40000.00,credit,SHARED-REF")
        self.assertEqual(upload(self.client, text, org="northwind").json()["imported_count"], 1)
        bluebird = upload(self.client, text, org="bluebird").json()
        self.assertEqual((bluebird["imported_count"], bluebird["duplicate_count"]), (1, 0))
        self.assertEqual(BankTransaction.objects.filter(bank_reference="SHARED-REF").count(), 2)
        # Only Bluebird has CC-2001, so only Bluebird's copy gets a suggestion.
        self.assertEqual(tx("SHARED-REF", "northwind").status, "needs_review")
        self.assertEqual(tx("SHARED-REF", "bluebird").status, "suggested")


class ImportTimeMatchingTests(APITestCase):
    """Test 4 (integration): reference matching runs during import."""

    def setUp(self):
        seed()

    def test_reference_matches_and_partial_payment(self):
        upload(
            self.client,
            csv_text(
                "2026-04-04,ACH CREDIT HALLER CAPITAL LLC CC-1001,20000.00,credit,ACH1",
                "2026-04-14,ACH CREDIT HALLER CAPITAL cc1001,7500.00,credit,ACH2",
                "2026-03-20,WIRE INCOMING OAKRIDGE HOLDINGS LLC REF CC-1006,15000.00,credit,FT3",
            ),
        )
        for ref, amount in (("ACH1", "20,000.00"), ("ACH2", "7,500.00")):
            self.assertEqual(tx(ref).status, "suggested")
            (match,) = proposed(ref)
            self.assertEqual(match.line_item, line_item("CC-1001"))
            self.assertEqual(
                match.reason, f"Reference CC-1001 found; partial payment of {amount} against 27,500.00 remaining."
            )
        # Call #2 is dated after this transaction, so CC-1006 is not eligible.
        future = tx("FT3")
        self.assertEqual(future.status, "needs_review")
        self.assertEqual(proposed("FT3"), [])
        self.assertIn("CC-1006 found but not eligible", future.review_reason)

    def test_import_query_count_does_not_grow_with_rows(self):
        rows = [f"2026-04-{(i % 28) + 1:02d},WIRE INCOMING PATEL FAMILY TRUST,12500.00,credit,BULK{i}" for i in range(3000)]
        with CaptureQueriesContext(connection) as queries:
            body = upload(self.client, csv_text(*rows)).json()
        self.assertEqual(body["imported_count"], 3000)
        self.assertLess(len(queries), 15)


@skipUnless(SAMPLE_CSV.exists(), "sample_bank_statement.csv not found at the repository root")
class SuppliedSampleFileTests(APITestCase):
    """End-to-end import of the supplied sample_bank_statement.csv for Northwind."""

    def setUp(self):
        seed()

    def test_sample_file(self):
        body = upload(self.client, SAMPLE_CSV.read_text()).json()
        self.assertEqual(body["imported_count"], 11)
        self.assertEqual(body["duplicate_count"], 1)
        self.assertEqual(body["error_count"], 2)
        self.assertEqual([e["line"] for e in body["errors"]], [13, 14])
        self.assertEqual(body["duplicates"][0]["line"], 11)

        expected = {
            "FT20260403A": ("suggested", ["CC-1002"]),
            "ACH20260404B": ("suggested", ["CC-1001"]),
            "FEE20260405": ("ignored", []),
            "FT20260407C": ("suggested", ["CC-1003"]),
            "FT20260408E": ("suggested", ["CC-1004"]),
            "FT20260409D": ("needs_review", []),
            "FT20260411G": ("needs_review", ["CC-1005", "CC-1006"]),
            "ACH20260414H": ("suggested", ["CC-1001"]),
            "FT20260415J": ("needs_review", []),  # overpayment
            "FT20260416K": ("needs_review", []),  # Bluebird's reference
            "FT20260320N": ("needs_review", []),  # before Call #2
        }
        actual = {
            t.bank_reference: (t.status, [m.line_item.expected_wire_reference for m in proposed(t.bank_reference)])
            for t in BankTransaction.objects.all()
        }
        self.assertEqual(actual, expected)
        for t in BankTransaction.objects.filter(status="needs_review"):
            self.assertTrue(t.review_reason)
