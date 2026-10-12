"""Test 8: organization header handling and tenant isolation."""

from decimal import Decimal

from django.db import IntegrityError, connection, transaction
from rest_framework.test import APITestCase

from reconciliation.models import BankTransaction, ReconciliationMatch

from .helpers import csv_text, get, line_item, org, post, proposed, seed, tx, upload


class OrganizationHeaderTests(APITestCase):
    def setUp(self):
        seed()

    def test_missing_header_is_400(self):
        for url in ("/api/transactions/", "/api/line-items/"):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["error"]["code"], "missing_organization")
        self.assertEqual(self.client.post("/api/matches/1/approve/").status_code, 400)

    def test_unknown_organization_is_404(self):
        response = get(self.client, "/api/transactions/", org="acme")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "unknown_organization")

    def test_header_free_endpoints(self):
        self.assertEqual(self.client.get("/api/health/").json(), {"status": "ok", "database": "ok"})
        slugs = [o["slug"] for o in self.client.get("/api/organizations/").json()]
        self.assertEqual(sorted(slugs), ["bluebird", "northwind"])


class TenantIsolationTests(APITestCase):
    def setUp(self):
        seed()
        upload(
            self.client,
            csv_text("2026-04-03,WIRE INCOMING RAHUL SHAH TRUST REF CC-1002,25000.00,credit,NW-1"),
            org="northwind",
        )
        upload(
            self.client,
            csv_text("2026-04-16,WIRE INCOMING CEDAR GROVE FUND CC-2001,40000.00,credit,BB-1"),
            org="bluebird",
        )
        self.bluebird_tx = tx("BB-1", "bluebird")
        (self.bluebird_match,) = proposed("BB-1", "bluebird")

    def test_lists_are_scoped(self):
        refs = [t["bank_reference"] for t in get(self.client, "/api/transactions/").json()]
        self.assertEqual(refs, ["NW-1"])
        items = [i["expected_wire_reference"] for i in get(self.client, "/api/line-items/").json()]
        self.assertNotIn("CC-2001", items)
        self.assertEqual(len(items), 6)
        bluebird_items = get(self.client, "/api/line-items/", org="bluebird").json()
        self.assertEqual([i["expected_wire_reference"] for i in bluebird_items], ["CC-2001"])

    def test_cross_tenant_access_returns_404_and_changes_nothing(self):
        bb_tx, bb_match = self.bluebird_tx, self.bluebird_match
        self.assertEqual(get(self.client, f"/api/transactions/{bb_tx.pk}/").status_code, 404)
        self.assertEqual(post(self.client, f"/api/matches/{bb_match.pk}/approve/").status_code, 404)
        self.assertEqual(post(self.client, f"/api/matches/{bb_match.pk}/reject/").status_code, 404)
        self.assertEqual(post(self.client, f"/api/transactions/{bb_tx.pk}/ignore/").status_code, 404)

        self.assertEqual(line_item("CC-2001").amount_funded, Decimal("0.00"))
        bb_match.refresh_from_db()
        bb_tx.refresh_from_db()
        self.assertEqual((bb_match.status, bb_tx.status), ("proposed", "suggested"))

        # The owner can still act on it.
        self.assertEqual(get(self.client, f"/api/transactions/{bb_tx.pk}/", org="bluebird").status_code, 200)
        self.assertEqual(post(self.client, f"/api/matches/{bb_match.pk}/approve/", org="bluebird").status_code, 200)

    def test_organization_in_body_is_ignored(self):
        response = self.client.post(
            f"/api/matches/{self.bluebird_match.pk}/approve/",
            {"organization": "bluebird", "organization_id": org("bluebird").pk},
            format="json",
            HTTP_X_ORGANIZATION="northwind",
        )
        self.assertEqual(response.status_code, 404)

    def test_database_refuses_cross_organization_match(self):
        nw_tx = tx("NW-1")
        with self.assertRaises(IntegrityError), transaction.atomic():
            ReconciliationMatch.objects.create(
                organization=nw_tx.organization,
                transaction=nw_tx,
                line_item=line_item("CC-2001"),  # Bluebird's line item
                reason="cross-tenant",
            )
            with connection.cursor() as cursor:
                cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        self.assertFalse(BankTransaction.objects.filter(organization=org("bluebird"), bank_reference="NW-1").exists())
