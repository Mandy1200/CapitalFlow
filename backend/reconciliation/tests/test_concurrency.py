"""Concurrent approvals against real PostgreSQL row locks."""

import threading
from decimal import Decimal

from django.db import connection
from django.test import TransactionTestCase, skipUnlessDBFeature
from rest_framework.test import APIClient

from reconciliation.models import ReconciliationMatch

from .helpers import csv_text, line_item, proposed, seed, tx, upload


def run_in_parallel(urls: list[str]) -> list[int]:
    """POST every URL at the same moment from its own thread and DB connection."""
    barrier = threading.Barrier(len(urls))
    results = [None] * len(urls)

    def worker(index, url):
        try:
            client = APIClient()
            barrier.wait()
            results[index] = client.post(url, HTTP_X_ORGANIZATION="northwind").status_code
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=(i, url)) for i, url in enumerate(urls)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results


@skipUnlessDBFeature("has_select_for_update")
class ConcurrentApprovalTests(TransactionTestCase):
    def setUp(self):
        seed()
        upload(
            APIClient(),
            csv_text(
                "2026-04-03,WIRE INCOMING RAHUL SHAH TRUST REF CC-1002,25000.00,credit,FULL",
                "2026-04-11,WIRE INCOMING OAKRIDGE HOLDINGS LLC,15000.00,credit,AMBIG",
                "2026-04-04,HALLER CAPITAL CC-1001,20000.00,credit,H1",
                "2026-04-05,HALLER CAPITAL CC-1001,20000.00,credit,H2",
            ),
        )

    def test_same_approval_submitted_concurrently_funds_once(self):
        (match,) = proposed("FULL")
        results = run_in_parallel([f"/api/matches/{match.pk}/approve/"] * 6)
        self.assertEqual(sorted(results), [200, 409, 409, 409, 409, 409])
        self.assertEqual(line_item("CC-1002").amount_funded, Decimal("25000.00"))

    def test_two_candidates_of_one_transaction_approved_concurrently(self):
        first, second = proposed("AMBIG")
        results = run_in_parallel([f"/api/matches/{first.pk}/approve/", f"/api/matches/{second.pk}/approve/"])
        self.assertEqual(sorted(results), [200, 409])
        funded = line_item("CC-1005").amount_funded + line_item("CC-1006").amount_funded
        self.assertEqual(funded, Decimal("15000.00"))
        self.assertEqual(
            ReconciliationMatch.objects.filter(transaction=tx("AMBIG"), status="approved").count(), 1
        )

    def test_two_transactions_racing_for_one_line_item_cannot_overfund(self):
        # 20,000 + 20,000 against 27,500 called: only one can win.
        (h1,) = proposed("H1")
        (h2,) = proposed("H2")
        results = run_in_parallel([f"/api/matches/{h1.pk}/approve/", f"/api/matches/{h2.pk}/approve/"])
        self.assertEqual(sorted(results), [200, 409])
        item = line_item("CC-1001")
        self.assertEqual((item.amount_funded, item.status), (Decimal("20000.00"), "partially_funded"))


@skipUnlessDBFeature("has_select_for_update")
class ConcurrentImportTests(TransactionTestCase):
    def setUp(self):
        seed()

    def test_same_file_imported_concurrently_is_stored_once(self):
        text = csv_text(*[f"2026-04-05,WIRE {i},100.00,credit,REF{i}" for i in range(200)])
        barrier = threading.Barrier(3)
        bodies = []

        def worker():
            try:
                barrier.wait()
                bodies.append(upload(APIClient(), text).json())
            finally:
                connection.close()

        threads = [threading.Thread(target=worker) for _ in range(3)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sorted(b["imported_count"] for b in bodies), [0, 0, 200])
        self.assertEqual(sorted(b["duplicate_count"] for b in bodies), [0, 200, 200])
        self.assertEqual(tx("REF0").organization.transactions.count(), 200)
