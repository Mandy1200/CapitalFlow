from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from reconciliation.models import (
    BankTransaction,
    CapitalCall,
    InvestorEntity,
    LineItem,
    Organization,
)

DEMO_DATA = [
    {
        "slug": "northwind",
        "name": "Northwind Ventures",
        "calls": [
            {
                "call_number": 1,
                "call_date": date(2026, 3, 25),
                "due_date": date(2026, 4, 10),
                "line_items": [
                    ("Haller Capital LLC", "CC-1001", "27500.00"),
                    ("Rahul Shah Trust", "CC-1002", "25000.00"),
                    ("Patel Family Trust", "CC-1003", "12500.00"),
                    ("Meridian Partners LP", "CC-1004", "15000.00"),
                    ("Oakridge Holdings LLC", "CC-1005", "15000.00"),
                ],
            },
            {
                "call_number": 2,
                "call_date": date(2026, 4, 1),
                "due_date": date(2026, 4, 20),
                "line_items": [("Oakridge Holdings LLC", "CC-1006", "15000.00")],
            },
        ],
    },
    {
        "slug": "bluebird",
        "name": "Bluebird Capital",
        "calls": [
            {
                "call_number": 1,
                "call_date": date(2026, 4, 1),
                "due_date": date(2026, 4, 15),
                "line_items": [("Cedar Grove Fund LP", "CC-2001", "40000.00")],
            }
        ],
    },
]


class Command(BaseCommand):
    help = "Seed the demo organizations, capital calls and line items (safe to run repeatedly)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Also delete the demo organizations' imported transactions and reset funding to zero.",
        )

    @transaction.atomic
    def handle(self, *args, reset=False, **options):
        created = 0
        for org_data in DEMO_DATA:
            org, was_created = Organization.objects.get_or_create(
                slug=org_data["slug"], defaults={"name": org_data["name"]}
            )
            created += was_created
            if org.name != org_data["name"]:
                org.name = org_data["name"]
                org.save(update_fields=["name"])

            for call_data in org_data["calls"]:
                call, was_created = CapitalCall.objects.get_or_create(
                    organization=org,
                    call_number=call_data["call_number"],
                    defaults={"call_date": call_data["call_date"], "due_date": call_data["due_date"]},
                )
                created += was_created
                for investor_name, reference, amount in call_data["line_items"]:
                    investor, was_created = InvestorEntity.objects.get_or_create(organization=org, name=investor_name)
                    created += was_created
                    _, was_created = LineItem.objects.get_or_create(
                        organization=org,
                        expected_wire_reference=reference,
                        defaults={
                            "capital_call": call,
                            "investor_entity": investor,
                            "amount_called": Decimal(amount),
                            "amount_funded": Decimal("0.00"),
                            "status": LineItem.Status.OPEN,
                        },
                    )
                    created += was_created

            if reset:
                deleted, _ = BankTransaction.objects.filter(organization=org).delete()  # matches cascade
                LineItem.objects.filter(organization=org).update(
                    amount_funded=Decimal("0.00"), status=LineItem.Status.OPEN
                )
                self.stdout.write(f"Reset {org.slug}: deleted {deleted} transaction/match rows.")

        self.stdout.write(self.style.SUCCESS(f"Demo data ready ({created} new rows)."))
