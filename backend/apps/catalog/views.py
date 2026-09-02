from __future__ import annotations

from django.db.models import Count, Sum
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core import capabilities as caps
from apps.core.audit import record_audit
from apps.core.views import ActiveByDefaultMixin, TenantModelViewSet
from apps.inventory.services import zero_out_stock
from apps.subscriptions.limits import enforce_limit

from .filters import CategoryFilter, ProductFilter, ProductVariantFilter
from .models import Brand, Category, Product, ProductVariant
from .serializers import BrandSerializer, CategorySerializer, ProductSerializer, ProductVariantSerializer


class CategoryViewSet(TenantModelViewSet):
    serializer_class = CategorySerializer
    model = Category
    read_capability = caps.PRODUCTS_READ
    write_capability = caps.PRODUCTS_WRITE
    filterset_class = CategoryFilter
    search_fields = ["name"]


class BrandViewSet(TenantModelViewSet):
    serializer_class = BrandSerializer
    model = Brand
    read_capability = caps.PRODUCTS_READ
    write_capability = caps.PRODUCTS_WRITE
    filterset_fields = ["is_active"]
    search_fields = ["name"]


class ProductViewSet(ActiveByDefaultMixin, TenantModelViewSet):
    serializer_class = ProductSerializer
    model = Product
    select_related = ("category", "brand")
    prefetch_related = ("variants",)
    read_capability = caps.PRODUCTS_READ
    write_capability = caps.PRODUCTS_WRITE
    filterset_class = ProductFilter
    search_fields = ["name", "description", "variants__sku", "variants__barcode"]
    ordering_fields = ["name", "created_at"]

    def perform_create(self, serializer):
        enforce_limit(
            organization=self.request.organization,
            resource="products",
            current_count=Product.objects.count(),
        )
        super().perform_create(serializer)
        record_audit(
            organization=self.request.organization,
            action="product.created",
            actor=self.request.user,
            obj=serializer.instance,
            metadata={"name": serializer.instance.name},
        )

    def perform_destroy(self, instance):
        # Products are referenced by sales and the inventory ledger.
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])
        variants = list(instance.variants.all())
        instance.variants.update(is_active=False)
        for variant in variants:
            zero_out_stock(organization=self.request.organization, variant=variant, user=self.request.user)


class ProductVariantViewSet(ActiveByDefaultMixin, TenantModelViewSet):
    serializer_class = ProductVariantSerializer
    model = ProductVariant
    select_related = ("product", "product__brand")
    read_capability = caps.PRODUCTS_READ
    write_capability = caps.PRODUCTS_WRITE
    filterset_class = ProductVariantFilter
    search_fields = ["sku", "barcode", "product__name", "size", "color"]
    ordering_fields = ["sku", "price", "created_at"]

    @extend_schema(
        parameters=[OpenApiParameter("barcode", str, required=True)],
        responses={200: ProductVariantSerializer},
    )
    @action(detail=False, methods=["get"])
    def lookup(self, request):
        """Barcode scan endpoint for the POS. Also matches on exact SKU."""
        code = (request.query_params.get("barcode") or "").strip()
        if not code:
            return Response({"detail": "barcode is required.", "code": "missing_barcode"}, status=400)

        variant = self.get_queryset().filter(barcode=code).first() or self.get_queryset().filter(
            sku=code
        ).first()
        if variant is None:
            return Response({"detail": "No variant matches that code.", "code": "not_found"}, status=404)
        return Response(self.get_serializer(variant).data)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        totals = self.get_queryset().aggregate(
            variants=Count("id"), retail_value=Sum("price")
        )
        return Response(totals)

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])
        zero_out_stock(organization=self.request.organization, variant=instance, user=self.request.user)
