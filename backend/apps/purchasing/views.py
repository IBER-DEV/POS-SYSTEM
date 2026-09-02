from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core import capabilities as caps
from apps.core.views import IdempotentActionMixin, TenantModelViewSet, TenantViewSetMixin
from apps.organizations.selectors import default_location

from .filters import PurchaseFilter, SupplierFilter
from .models import Purchase, Supplier
from .serializers import PurchaseCreateSerializer, PurchaseSerializer, SupplierSerializer
from .services import cancel_purchase, create_purchase, receive_purchase


class SupplierViewSet(TenantModelViewSet):
    serializer_class = SupplierSerializer
    model = Supplier
    read_capability = caps.SUPPLIERS_READ
    write_capability = caps.SUPPLIERS_WRITE
    filterset_class = SupplierFilter
    search_fields = ["name", "tax_id", "contact_name", "phone", "email"]

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])


class PurchaseViewSet(
    IdempotentActionMixin,
    TenantViewSetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Purchases are created and received, never edited in place.

    Editing a received purchase would silently rewrite the origin of stock the
    ledger already recorded.
    """

    serializer_class = PurchaseSerializer
    model = Purchase
    select_related = ("supplier", "location", "created_by", "received_by")
    prefetch_related = ("items", "items__variant", "items__variant__product")
    read_capability = caps.PURCHASES_READ
    write_capability = caps.PURCHASES_CREATE
    filterset_class = PurchaseFilter
    search_fields = ["number", "supplier_invoice", "supplier__name"]
    ordering_fields = ["purchased_at", "created_at", "total_cost"]

    @extend_schema(request=PurchaseCreateSerializer, responses={201: PurchaseSerializer})
    def create(self, request):
        return self.run_idempotent(
            request, endpoint="purchase.create", handler=lambda: self._create(request)
        )

    def _create(self, request):
        serializer = PurchaseCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        location = data.get("location") or default_location()
        if location is None:
            return Response(
                {"detail": "This organization has no active location.", "code": "no_location"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        purchase = create_purchase(
            organization=request.organization,
            location=location,
            supplier=data.get("supplier"),
            items=data["items"],
            user=request.user,
            supplier_invoice=data.get("supplier_invoice", ""),
            purchased_at=data.get("purchased_at"),
            notes=data.get("notes", ""),
        )
        if data["receive"]:
            purchase = receive_purchase(purchase=purchase, user=request.user)

        purchase = self.get_queryset().get(pk=purchase.pk)
        return Response(PurchaseSerializer(purchase).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses={200: PurchaseSerializer})
    @action(detail=True, methods=["post"])
    def receive(self, request, pk=None):
        purchase = receive_purchase(purchase=self.get_object(), user=request.user)
        return Response(PurchaseSerializer(self.get_queryset().get(pk=purchase.pk)).data)

    @extend_schema(request=None, responses={200: PurchaseSerializer})
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        purchase = cancel_purchase(
            purchase=self.get_object(),
            user=request.user,
            reason=request.data.get("reason", ""),
        )
        return Response(PurchaseSerializer(self.get_queryset().get(pk=purchase.pk)).data)
