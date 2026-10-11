from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q

MONEY_MAX_DIGITS = 14
MONEY_DECIMAL_PLACES = 2
ZERO = Decimal("0.00")


def money_field(**kwargs):
    return models.DecimalField(max_digits=MONEY_MAX_DIGITS, decimal_places=MONEY_DECIMAL_PLACES, **kwargs)


class Organization(models.Model):
    slug = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=200)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class InvestorEntity(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="investors")
    name = models.CharField(max_length=200)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "name"], name="investor_org_name_unique"),
            models.UniqueConstraint(fields=["id", "organization"], name="investor_id_org_unique"),
        ]

    def __str__(self):
        return self.name


class CapitalCall(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="capital_calls")
    call_number = models.PositiveIntegerField()
    call_date = models.DateField()
    due_date = models.DateField()

    class Meta:
        ordering = ["call_date", "call_number"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "call_number"], name="capital_call_org_number_unique"),
            models.UniqueConstraint(fields=["id", "organization"], name="capital_call_id_org_unique"),
            models.CheckConstraint(condition=Q(due_date__gte=F("call_date")), name="capital_call_due_after_call"),
        ]

    def __str__(self):
        return f"Call #{self.call_number}"


class LineItem(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        PARTIALLY_FUNDED = "partially_funded", "Partially funded"
        FUNDED = "funded", "Funded"

    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="line_items")
    capital_call = models.ForeignKey(CapitalCall, on_delete=models.PROTECT, related_name="line_items")
    investor_entity = models.ForeignKey(InvestorEntity, on_delete=models.PROTECT, related_name="line_items")
    expected_wire_reference = models.CharField(max_length=64)
    amount_called = money_field()
    amount_funded = money_field(default=ZERO)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)

    class Meta:
        ordering = ["capital_call__call_date", "expected_wire_reference"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "expected_wire_reference"], name="line_item_org_reference_unique"
            ),
            models.UniqueConstraint(fields=["id", "organization"], name="line_item_id_org_unique"),
            models.CheckConstraint(condition=Q(amount_called__gt=0), name="line_item_called_positive"),
            models.CheckConstraint(condition=Q(amount_funded__gte=0), name="line_item_funded_non_negative"),
            # The last line of defence against overfunding.
            models.CheckConstraint(
                condition=Q(amount_funded__lte=F("amount_called")), name="line_item_funded_not_above_called"
            ),
        ]
        indexes = [models.Index(fields=["organization", "status"], name="line_item_org_status_idx")]

    def __str__(self):
        return f"{self.expected_wire_reference} ({self.investor_entity_id})"

    @property
    def remaining_amount(self) -> Decimal:
        return self.amount_called - self.amount_funded

    @staticmethod
    def status_for(amount_funded: Decimal, amount_called: Decimal) -> str:
        if amount_funded <= ZERO:
            return LineItem.Status.OPEN
        if amount_funded < amount_called:
            return LineItem.Status.PARTIALLY_FUNDED
        return LineItem.Status.FUNDED

    def clean(self):
        org_id = self.organization_id
        if self.capital_call_id and self.capital_call.organization_id != org_id:
            raise ValidationError("Capital call belongs to a different organization.")
        if self.investor_entity_id and self.investor_entity.organization_id != org_id:
            raise ValidationError("Investor belongs to a different organization.")


class BankTransaction(models.Model):
    class Type(models.TextChoices):
        CREDIT = "credit", "Credit"
        DEBIT = "debit", "Debit"

    class Status(models.TextChoices):
        SUGGESTED = "suggested", "Suggested"
        NEEDS_REVIEW = "needs_review", "Needs review"
        RECONCILED = "reconciled", "Reconciled"
        IGNORED = "ignored", "Ignored"

    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="transactions")
    transaction_date = models.DateField()
    description = models.TextField()
    amount = money_field()
    type = models.CharField(max_length=10, choices=Type.choices)
    bank_reference = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=Status.choices)
    review_reason = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-transaction_date", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "bank_reference"], name="transaction_org_reference_unique"),
            models.UniqueConstraint(fields=["id", "organization"], name="transaction_id_org_unique"),
            models.CheckConstraint(
                condition=(Q(type="credit", amount__gt=0) | Q(type="debit", amount__lt=0)),
                name="transaction_amount_sign_matches_type",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "-transaction_date"], name="transaction_org_date_idx"),
            models.Index(fields=["organization", "status"], name="transaction_org_status_idx"),
        ]

    def __str__(self):
        return f"{self.bank_reference} {self.amount}"


class ReconciliationMatch(models.Model):
    class Status(models.TextChoices):
        PROPOSED = "proposed", "Proposed"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="matches")
    transaction = models.ForeignKey(BankTransaction, on_delete=models.CASCADE, related_name="matches")
    line_item = models.ForeignKey(LineItem, on_delete=models.PROTECT, related_name="matches")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PROPOSED)
    reason = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["transaction", "line_item"], name="match_transaction_line_item_unique"),
            # A bank transaction can fund at most one line item.
            models.UniqueConstraint(
                fields=["transaction"],
                condition=Q(status="approved"),
                name="match_one_approved_per_transaction",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "status"], name="match_org_status_idx"),
            models.Index(fields=["line_item", "status"], name="match_line_item_status_idx"),
        ]

    def __str__(self):
        return f"Match {self.transaction_id} -> {self.line_item_id} ({self.status})"

    def clean(self):
        org_id = self.organization_id
        if self.transaction_id and self.transaction.organization_id != org_id:
            raise ValidationError("Transaction belongs to a different organization.")
        if self.line_item_id and self.line_item.organization_id != org_id:
            raise ValidationError("Line item belongs to a different organization.")
