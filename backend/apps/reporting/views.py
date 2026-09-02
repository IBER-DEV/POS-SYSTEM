from __future__ import annotations

from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core import capabilities as caps
from apps.core.permissions import HasCapability, HasOrganization
from apps.organizations.models import Location

from . import selectors
from .serializers import (
    CashSessionsReportSerializer,
    InventoryValuationSerializer,
    MarginSerializer,
    RefundsSummarySerializer,
    ReportIndexSerializer,
    SalesSummarySerializer,
    TopProductSerializer,
)

PERIOD_PARAMS = [
    OpenApiParameter("from", str, description="ISO-8601 start. Defaults to 30 days ago."),
    OpenApiParameter("to", str, description="ISO-8601 end. Defaults to now."),
    OpenApiParameter("location", str, description="Restrict to one location."),
]


class ReportViewSet(viewsets.ViewSet):
    """Read-only aggregates. Every figure is derived, never stored."""

    permission_classes = [HasOrganization, HasCapability]
    read_capability = caps.REPORTS_READ
    write_capability = caps.REPORTS_READ
    serializer_class = ReportIndexSerializer

    def _period(self, request):
        def parse(value):
            if not value:
                return None
            parsed = timezone.datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if timezone.is_aware(parsed) else timezone.make_aware(parsed)

        return selectors.resolve_period(
            parse(request.query_params.get("from")), parse(request.query_params.get("to"))
        )

    def _location(self, request):
        location_id = request.query_params.get("location")
        return Location.objects.filter(pk=location_id).first() if location_id else None

    @extend_schema(parameters=PERIOD_PARAMS, responses={200: SalesSummarySerializer})
    @action(detail=False, methods=["get"], url_path="sales-summary")
    def sales_summary(self, request):
        date_from, date_to = self._period(request)
        return Response(
            selectors.sales_summary(
                date_from=date_from, date_to=date_to, location=self._location(request)
            )
        )

    @extend_schema(
        parameters=PERIOD_PARAMS + [OpenApiParameter("limit", int, description="Default 10.")],
        responses={200: TopProductSerializer(many=True)},
    )
    @action(detail=False, methods=["get"], url_path="top-products")
    def top_products(self, request):
        date_from, date_to = self._period(request)
        limit = min(int(request.query_params.get("limit", 10)), 100)
        return Response(
            selectors.top_products(
                date_from=date_from,
                date_to=date_to,
                location=self._location(request),
                limit=limit,
            )
        )

    @extend_schema(parameters=PERIOD_PARAMS, responses={200: MarginSerializer})
    @action(detail=False, methods=["get"])
    def margin(self, request):
        date_from, date_to = self._period(request)
        return Response(
            selectors.margin_report(
                date_from=date_from, date_to=date_to, location=self._location(request)
            )
        )

    @extend_schema(
        parameters=[OpenApiParameter("location", str)],
        responses={200: InventoryValuationSerializer},
    )
    @action(detail=False, methods=["get"], url_path="inventory-valuation")
    def inventory_valuation(self, request):
        return Response(selectors.inventory_valuation(location=self._location(request)))

    @extend_schema(parameters=PERIOD_PARAMS, responses={200: CashSessionsReportSerializer})
    @action(detail=False, methods=["get"], url_path="cash-sessions")
    def cash_sessions(self, request):
        date_from, date_to = self._period(request)
        return Response(
            selectors.cash_sessions_report(
                date_from=date_from, date_to=date_to, location=self._location(request)
            )
        )

    @extend_schema(parameters=PERIOD_PARAMS, responses={200: RefundsSummarySerializer})
    @action(detail=False, methods=["get"])
    def refunds(self, request):
        date_from, date_to = self._period(request)
        return Response(
            selectors.refunds_summary(
                date_from=date_from, date_to=date_to, location=self._location(request)
            )
        )

    @extend_schema(responses={200: ReportIndexSerializer})
    def list(self, request):
        """Index of the available reports, so a client can discover them."""
        return Response(
            {
                "reports": [
                    "sales-summary",
                    "top-products",
                    "margin",
                    "inventory-valuation",
                    "cash-sessions",
                    "refunds",
                ]
            }
        )
