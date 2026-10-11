from rest_framework import serializers

from .models import BankTransaction, CapitalCall, LineItem, Organization, ReconciliationMatch


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ["id", "slug", "name"]


class CapitalCallSerializer(serializers.ModelSerializer):
    class Meta:
        model = CapitalCall
        fields = ["id", "call_number", "call_date", "due_date"]


class LineItemSerializer(serializers.ModelSerializer):
    investor_name = serializers.CharField(source="investor_entity.name")
    capital_call = CapitalCallSerializer()
    remaining_amount = serializers.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        model = LineItem
        fields = [
            "id",
            "investor_entity_id",
            "investor_name",
            "capital_call",
            "expected_wire_reference",
            "amount_called",
            "amount_funded",
            "remaining_amount",
            "status",
        ]


class MatchSerializer(serializers.ModelSerializer):
    line_item_id = serializers.IntegerField(source="line_item.id")
    investor_name = serializers.CharField(source="line_item.investor_entity.name")
    expected_wire_reference = serializers.CharField(source="line_item.expected_wire_reference")
    capital_call_number = serializers.IntegerField(source="line_item.capital_call.call_number")
    amount_called = serializers.DecimalField(source="line_item.amount_called", max_digits=14, decimal_places=2)
    remaining_amount = serializers.DecimalField(
        source="line_item.remaining_amount", max_digits=14, decimal_places=2
    )
    line_item_status = serializers.CharField(source="line_item.status")

    class Meta:
        model = ReconciliationMatch
        fields = [
            "id",
            "status",
            "reason",
            "line_item_id",
            "investor_name",
            "expected_wire_reference",
            "capital_call_number",
            "amount_called",
            "remaining_amount",
            "line_item_status",
            "created_at",
        ]


class TransactionSerializer(serializers.ModelSerializer):
    matches = MatchSerializer(many=True)
    can_ignore = serializers.SerializerMethodField()

    class Meta:
        model = BankTransaction
        fields = [
            "id",
            "transaction_date",
            "description",
            "amount",
            "type",
            "bank_reference",
            "status",
            "review_reason",
            "created_at",
            "can_ignore",
            "matches",
        ]

    def get_can_ignore(self, obj) -> bool:
        return obj.type == BankTransaction.Type.CREDIT and obj.status in (
            BankTransaction.Status.SUGGESTED,
            BankTransaction.Status.NEEDS_REVIEW,
        )
