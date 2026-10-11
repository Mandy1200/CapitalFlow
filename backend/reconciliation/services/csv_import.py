# CSV bank statement import service: validation, duplicate detection, and matching.

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction

from ..models import BankTransaction, LineItem, Organization, ReconciliationMatch
from .matching import CandidateLineItem, match_transaction

REQUIRED_COLUMNS = ("date", "description", "amount", "type", "reference")

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Digits with optional, correctly placed thousands separators and up to 2 decimals.
_AMOUNT_RE = re.compile(r"^[+-]?(\d{1,3}(,\d{3})+|\d+)(\.\d{1,2})?$")
_MAX_INTEGER_DIGITS = 12
_MAX_REFERENCE_LENGTH = BankTransaction._meta.get_field("bank_reference").max_length


class CsvFileError(Exception):
    """The file as a whole is unusable; nothing is imported."""

    def __init__(self, message: str, details=None):
        super().__init__(message)
        self.message = message
        self.details = details


class ImportConflict(Exception):
    """A concurrent import stored one of this file's references first."""


@dataclass
class ImportSummary:
    imported_count: int = 0
    duplicate_count: int = 0
    error_count: int = 0
    credit_count: int = 0
    debit_count: int = 0
    suggested_count: int = 0
    needs_review_count: int = 0
    errors: list[dict] = field(default_factory=list)
    duplicates: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "imported_count": self.imported_count,
            "duplicate_count": self.duplicate_count,
            "error_count": self.error_count,
            "imported_breakdown": {
                "credits": self.credit_count,
                "debits": self.debit_count,
                "suggested": self.suggested_count,
                "needs_review": self.needs_review_count,
            },
            "errors": self.errors,
            "duplicates": self.duplicates,
        }


@dataclass(frozen=True)
class ParsedRow:
    line: int
    transaction_date: date
    description: str
    amount: Decimal
    type: str
    reference: str


def parse_date(value: str) -> date:
    if not _DATE_RE.match(value):
        raise ValueError(f"Invalid date '{value}'; expected YYYY-MM-DD.")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"Invalid date '{value}'; not a real calendar date.") from None


def parse_amount(value: str) -> Decimal:
    if not value:
        raise ValueError("Amount is required.")
    if not _AMOUNT_RE.match(value):
        raise ValueError(f"Invalid amount '{value}'.")
    # Note: Stripping commas from amounts like "25,000.00" before Decimal conversion
    try:
        amount = Decimal(value.replace(",", ""))
    except InvalidOperation:
        raise ValueError(f"Invalid amount '{value}'.") from None
    if len(str(abs(amount).to_integral_value())) > _MAX_INTEGER_DIGITS:
        raise ValueError(f"Amount '{value}' is too large.")
    if amount == 0:
        raise ValueError("Amount must not be zero.")
    return amount.quantize(Decimal("0.01"))


def parse_row(line: int, raw: dict[str, str]) -> ParsedRow:
    """Validate one row; raises ``ValueError`` with every problem found."""
    problems = []
    values = {column: (raw.get(column) or "").strip() for column in REQUIRED_COLUMNS}

    transaction_date = amount = None
    try:
        transaction_date = parse_date(values["date"])
    except ValueError as exc:
        problems.append(str(exc))

    description = values["description"]
    if not description:
        problems.append("Description is required.")

    try:
        amount = parse_amount(values["amount"])
    except ValueError as exc:
        problems.append(str(exc))

    tx_type = values["type"].lower()
    if tx_type not in (BankTransaction.Type.CREDIT, BankTransaction.Type.DEBIT):
        problems.append(f"Invalid type '{values['type']}'; expected credit or debit.")
    elif amount is not None:
        if tx_type == BankTransaction.Type.CREDIT and amount < 0:
            problems.append("Credit amount must be positive.")
        if tx_type == BankTransaction.Type.DEBIT and amount > 0:
            problems.append("Debit amount must be negative.")

    reference = values["reference"]
    if not reference:
        problems.append("Reference is required.")
    elif len(reference) > _MAX_REFERENCE_LENGTH:
        problems.append(f"Reference is longer than {_MAX_REFERENCE_LENGTH} characters.")

    if problems:
        raise ValueError(" ".join(problems))
    return ParsedRow(line, transaction_date, description, amount, tx_type, reference)


def read_rows(content: bytes):
    """Yield ``(physical_line_number, row_dict)`` after validating the header."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise CsvFileError("The file is not valid UTF-8 text.") from None
    if not text.strip():
        raise CsvFileError("The file is empty.")

    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        header = next(reader)
    except csv.Error as exc:
        raise CsvFileError(f"Could not read the CSV header: {exc}.") from None
    columns = [name.strip().lower() for name in header]
    missing = [name for name in REQUIRED_COLUMNS if name not in columns]
    if missing:
        raise CsvFileError(
            f"Missing required column(s): {', '.join(missing)}.",
            {"missing_columns": missing, "required_columns": list(REQUIRED_COLUMNS)},
        )
    index = {name: columns.index(name) for name in REQUIRED_COLUMNS}

    def rows():
        last_line = reader.line_num
        while True:
            start_line = last_line + 1
            try:
                record = next(reader)
            except StopIteration:
                return
            except csv.Error as exc:
                raise CsvFileError(f"Malformed CSV near line {start_line}: {exc}.") from None
            last_line = reader.line_num
            if not any(cell.strip() for cell in record):
                continue  # blank line
            if len(record) < len(columns):
                yield start_line, None
                continue
            yield start_line, {name: record[i] for name, i in index.items()}

    return rows()


def _candidate_line_items(organization: Organization) -> list[CandidateLineItem]:
    items = LineItem.objects.filter(organization=organization).select_related("capital_call", "investor_entity")
    return [
        CandidateLineItem(
            id=item.id,
            investor_name=item.investor_entity.name,
            expected_wire_reference=item.expected_wire_reference,
            call_number=item.capital_call.call_number,
            call_date=item.capital_call.call_date,
            remaining=item.remaining_amount,
        )
        for item in items
    ]


def import_bank_statement(*, organization: Organization, content: bytes) -> ImportSummary:
    rows = read_rows(content)  # raises CsvFileError before anything is touched
    summary = ImportSummary()
    parsed: list[ParsedRow] = []
    for line, raw in rows:
        if raw is None:
            summary.errors.append({"line": line, "message": "Row has fewer columns than the header."})
            continue
        try:
            parsed.append(parse_row(line, raw))
        except ValueError as exc:
            summary.errors.append({"line": line, "message": str(exc)})
    summary.error_count = len(summary.errors)

    try:
        with transaction.atomic():
            Organization.objects.select_for_update().get(pk=organization.pk)
            _store(organization, parsed, summary)
    except IntegrityError as exc:
        raise ImportConflict() from exc
    return summary


def _store(organization: Organization, parsed: list[ParsedRow], summary: ImportSummary) -> None:
    existing = set(
        BankTransaction.objects.filter(
            organization=organization, bank_reference__in={row.reference for row in parsed}
        ).values_list("bank_reference", flat=True)
    )
    seen_in_file: dict[str, int] = {}
    to_create: list[tuple[ParsedRow, BankTransaction, tuple]] = []
    line_items = None

    for row in parsed:
        if row.reference in existing:
            summary.duplicates.append(
                {"line": row.line, "reference": row.reference, "message": "Reference was already imported."}
            )
            continue
        if row.reference in seen_in_file:
            summary.duplicates.append(
                {
                    "line": row.line,
                    "reference": row.reference,
                    "message": f"Duplicate of line {seen_in_file[row.reference]} in this file.",
                }
            )
            continue
        seen_in_file[row.reference] = row.line

        proposals = ()
        if row.type == BankTransaction.Type.DEBIT:
            status, review_reason = BankTransaction.Status.IGNORED, "Debit transactions are not matched."
        else:
            if line_items is None:
                line_items = _candidate_line_items(organization)
            outcome = match_transaction(
                transaction_date=row.transaction_date,
                description=row.description,
                amount=row.amount,
                bank_reference=row.reference,
                line_items=line_items,
            )
            status, review_reason, proposals = outcome.status, outcome.review_reason, outcome.proposals

        tx = BankTransaction(
            organization=organization,
            transaction_date=row.transaction_date,
            description=row.description,
            amount=row.amount,
            type=row.type,
            bank_reference=row.reference,
            status=status,
            review_reason=review_reason,
        )
        to_create.append((row, tx, proposals))

    created = BankTransaction.objects.bulk_create([tx for _, tx, _ in to_create])
    ReconciliationMatch.objects.bulk_create(
        [
            ReconciliationMatch(
                organization=organization,
                transaction=tx,
                line_item_id=proposal.line_item_id,
                status=ReconciliationMatch.Status.PROPOSED,
                reason=proposal.reason,
            )
            for (_, _, proposals), tx in zip(to_create, created)
            for proposal in proposals
        ]
    )

    summary.duplicate_count = len(summary.duplicates)
    summary.imported_count = len(created)
    for tx in created:
        if tx.type == BankTransaction.Type.CREDIT:
            summary.credit_count += 1
        else:
            summary.debit_count += 1
        if tx.status == BankTransaction.Status.SUGGESTED:
            summary.suggested_count += 1
        elif tx.status == BankTransaction.Status.NEEDS_REVIEW:
            summary.needs_review_count += 1
