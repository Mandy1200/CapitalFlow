from decimal import Decimal

from django.core.management import call_command
from rest_framework.test import APITestCase

from reconciliation.models import BankTransaction, CapitalCall, InvestorEntity, LineItem, Organization

from .helpers import _Null, csv_text, line_item, post, proposed, seed, upload


class SeedDemoTests(APITestCase):
    def counts(self):
        return [m.objects.count() for m in (Organization, InvestorEntity, CapitalCall, LineItem)]

    def test_seed_is_idempotent_and_matches_spec(self):
        seed()
        first = self.counts()
        seed()
        seed()
        self.assertEqual(self.counts(), first)
        self.assertEqual(first, [2, 6, 3, 7])  # Oakridge is one investor with two line items

        northwind = Organization.objects.get(slug="northwind")
        self.assertEqual(northwind.name, "Northwind Ventures")
        self.assertEqual(Organization.objects.get(slug="bluebird").name, "Bluebird Capital")
        call2 = CapitalCall.objects.get(organization=northwind, call_number=2)
        self.assertEqual((str(call2.call_date), str(call2.due_date)), ("2026-04-01", "2026-04-20"))
        self.assertEqual(line_item("CC-1001").amount_called, Decimal("27500.00"))
        self.assertEqual(line_item("CC-2001").organization.slug, "bluebird")
        for item in LineItem.objects.all():
            self.assertEqual((item.amount_funded, item.status), (Decimal("0.00"), "open"))
        self.assertEqual(BankTransaction.objects.count(), 0)

    def test_reseeding_keeps_funding_unless_reset(self):
        seed()
        upload(self.client, csv_text("2026-04-03,RAHUL SHAH TRUST CC-1002,25000.00,credit,R1"))
        post(self.client, f"/api/matches/{proposed('R1')[0].pk}/approve/")
        seed()
        self.assertEqual(line_item("CC-1002").amount_funded, Decimal("25000.00"))

        call_command("seed_demo", "--reset", stdout=_Null())
        self.assertEqual(BankTransaction.objects.count(), 0)
        self.assertEqual((line_item("CC-1002").amount_funded, line_item("CC-1002").status), (Decimal("0.00"), "open"))
