from datetime import date
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command

from reconciliation.models import BankTransaction, LineItem, Organization, ReconciliationMatch

HEADER = "date,description,amount,type,reference"


def seed():
    call_command("seed_demo", stdout=_Null())


def csv_text(*rows: str, header: str = HEADER) -> str:
    return "\n".join([header, *rows]) + "\n"


def upload(client, text: str, org: str = "northwind", name: str = "statement.csv"):
    file = SimpleUploadedFile(name, text.encode("utf-8"), content_type="text/csv")
    return client.post("/api/imports/", {"file": file}, format="multipart", HTTP_X_ORGANIZATION=org)


def post(client, url: str, org: str = "northwind"):
    return client.post(url, HTTP_X_ORGANIZATION=org)


def get(client, url: str, org: str = "northwind"):
    return client.get(url, HTTP_X_ORGANIZATION=org)


def org(slug: str) -> Organization:
    return Organization.objects.get(slug=slug)


def line_item(reference: str) -> LineItem:
    return LineItem.objects.get(expected_wire_reference=reference)


def tx(reference: str, org_slug: str = "northwind") -> BankTransaction:
    return BankTransaction.objects.get(bank_reference=reference, organization__slug=org_slug)


def proposed(reference: str, org_slug: str = "northwind") -> list[ReconciliationMatch]:
    return list(
        ReconciliationMatch.objects.filter(
            transaction__bank_reference=reference,
            organization__slug=org_slug,
            status=ReconciliationMatch.Status.PROPOSED,
        ).order_by("id")
    )


class _Null:
    def write(self, *_):
        pass


__all__ = ["date", "Decimal"]
