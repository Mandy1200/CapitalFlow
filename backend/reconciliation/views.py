from django.conf import settings
from django.db import connection
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .exceptions import Conflict, error_body
from .models import BankTransaction, LineItem, Organization, ReconciliationMatch
from .serializers import LineItemSerializer, OrganizationSerializer, TransactionSerializer
from .services import approvals
from .services.csv_import import CsvFileError, ImportConflict, import_bank_statement


def transactions_for(organization):
    matches = ReconciliationMatch.objects.select_related(
        "line_item__investor_entity", "line_item__capital_call"
    ).order_by("id")
    return BankTransaction.objects.filter(organization=organization).prefetch_related(
        Prefetch("matches", queryset=matches)
    )


def line_items_for(organization):
    return LineItem.objects.filter(organization=organization).select_related("investor_entity", "capital_call")


class HealthView(APIView):
    """Liveness plus a database round trip. Does not require X-Organization."""

    permission_classes = [AllowAny]

    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except Exception:
            return Response(
                error_body("database_unavailable", "Database is unavailable."),
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"status": "ok", "database": "ok"})


class ApiRootView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({
            "name": "CapitalFlow API",
            "version": "1.0",
            "endpoints": {
                "health": request.build_absolute_uri("health/"),
                "organizations": request.build_absolute_uri("organizations/"),
                "imports": request.build_absolute_uri("imports/"),
                "transactions": request.build_absolute_uri("transactions/"),
                "line_items": request.build_absolute_uri("line-items/"),
            },
            "headers": {
                "X-Organization": "Required on business endpoints (e.g. 'northwind' or 'bluebird')"
            }
        })


class OrganizationListView(APIView):
    """Organizations for the switcher. Does not require X-Organization."""

    permission_classes = [AllowAny]

    def get(self, request):
        return Response(OrganizationSerializer(Organization.objects.order_by("name"), many=True).data)


class ImportView(APIView):
    def post(self, request):
        upload = request.FILES.get("file")
        if upload is None:
            return Response(
                error_body("invalid", "Upload a CSV file in the 'file' form field."),
                status=status.HTTP_400_BAD_REQUEST,
            )
        if upload.size > settings.CSV_IMPORT_MAX_BYTES:
            return Response(
                error_body("file_too_large", f"The file exceeds {settings.CSV_IMPORT_MAX_BYTES} bytes."),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            summary = import_bank_statement(organization=request.organization, content=upload.read())
        except CsvFileError as exc:
            return Response(error_body("invalid_csv", exc.message, exc.details), status=status.HTTP_400_BAD_REQUEST)
        except ImportConflict:
            raise Conflict(
                "Another import stored some of these references at the same time; retry the upload.",
                "import_conflict",
            ) from None
        return Response(summary.as_dict(), status=status.HTTP_200_OK)


class TransactionListView(APIView):
    def get(self, request):
        queryset = transactions_for(request.organization)
        status_filter = request.query_params.get("status")
        if status_filter:
            if status_filter not in BankTransaction.Status.values:
                return Response(
                    error_body("invalid", f"Unknown status '{status_filter}'."), status=status.HTTP_400_BAD_REQUEST
                )
            queryset = queryset.filter(status=status_filter)
        return Response(TransactionSerializer(queryset.order_by("-transaction_date", "-id"), many=True).data)


class TransactionDetailView(APIView):
    def get(self, request, pk):
        tx = get_object_or_404(transactions_for(request.organization), pk=pk)
        return Response(TransactionSerializer(tx).data)


class TransactionIgnoreView(APIView):
    def post(self, request, pk):
        tx = approvals.ignore_transaction(organization=request.organization, transaction_id=pk)
        return Response(TransactionSerializer(transactions_for(request.organization).get(pk=tx.pk)).data)


class LineItemListView(APIView):
    def get(self, request):
        return Response(LineItemSerializer(line_items_for(request.organization), many=True).data)


class MatchActionView(APIView):
    match_action = None  # "approve" or "reject", set in urls.py

    def post(self, request, pk):
        org = request.organization
        if self.match_action == "approve":
            match = approvals.approve_match(organization=org, match_id=pk)
        else:
            match = approvals.reject_match(organization=org, match_id=pk)
        body = {
            "match_id": match.pk,
            "match_status": match.status,
            "transaction": TransactionSerializer(transactions_for(org).get(pk=match.transaction_id)).data,
            "line_item": LineItemSerializer(line_items_for(org).get(pk=match.line_item_id)).data,
        }
        return Response(body)
