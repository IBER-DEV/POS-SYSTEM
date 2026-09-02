from __future__ import annotations

from django.db.models import Count, Q, Sum
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core import capabilities as caps
from apps.core.views import TenantModelViewSet

from .filters import CustomerFilter
from .models import Customer
from .serializers import CustomerSerializer


class CustomerViewSet(TenantModelViewSet):
    serializer_class = CustomerSerializer
    model = Customer
    read_capability = caps.CUSTOMERS_READ
    write_capability = caps.CUSTOMERS_WRITE
    filterset_class = CustomerFilter
    search_fields = ["name", "phone", "email", "document_number"]
    ordering_fields = ["name", "created_at"]

    def get_queryset(self):
        # History is derived, never stored: one aggregate instead of a
        # denormalised counter that can drift.
        completed = Q(sales__status__in=["COMPLETED", "PARTIALLY_REFUNDED", "REFUNDED"])
        return (
            super()
            .get_queryset()
            .annotate(
                total_purchases=Count("sales", filter=completed, distinct=True),
                total_spent=Sum("sales__total", filter=completed),
            )
        )

    @extend_schema(responses={200: None})
    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        """Sales for this customer, most recent first."""
        from apps.sales.serializers import SaleListSerializer

        customer = self.get_object()
        sales = customer.sales.select_related("location").order_by("-occurred_at")
        page = self.paginate_queryset(sales)
        serializer = SaleListSerializer(page if page is not None else sales, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])
