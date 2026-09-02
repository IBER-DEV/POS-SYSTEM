from __future__ import annotations

from rest_framework import serializers

from apps.catalog.models import ProductVariant
from apps.core.fields import TenantPrimaryKeyRelatedField
from apps.core.serializers import TenantModelSerializer
from apps.organizations.models import Location

from .models import Purchase, PurchaseItem, Supplier


class SupplierSerializer(TenantModelSerializer):
    class Meta:
        model = Supplier
        fields = [
            "id",
            "name",
            "tax_id",
            "contact_name",
            "phone",
            "email",
            "address",
            "notes",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class PurchaseItemSerializer(TenantModelSerializer):
    variant_sku = serializers.CharField(source="variant.sku", read_only=True)
    variant_name = serializers.CharField(source="variant.display_name", read_only=True)

    class Meta:
        model = PurchaseItem
        fields = ["id", "variant", "variant_sku", "variant_name", "quantity", "unit_cost", "total_cost"]
        read_only_fields = ["id", "total_cost"]


class PurchaseSerializer(TenantModelSerializer):
    items = PurchaseItemSerializer(many=True, read_only=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    location_name = serializers.CharField(source="location.name", read_only=True)

    class Meta:
        model = Purchase
        fields = [
            "id",
            "number",
            "location",
            "location_name",
            "supplier",
            "supplier_name",
            "status",
            "supplier_invoice",
            "purchased_at",
            "received_at",
            "total_cost",
            "notes",
            "created_by",
            "received_by",
            "items",
            "created_at",
        ]
        read_only_fields = fields


class PurchaseItemInputSerializer(serializers.Serializer):
    variant = TenantPrimaryKeyRelatedField(queryset=ProductVariant.objects)
    quantity = serializers.IntegerField(min_value=1)
    unit_cost = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0)


class PurchaseCreateSerializer(serializers.Serializer):
    location = TenantPrimaryKeyRelatedField(queryset=Location.objects, required=False)
    supplier = TenantPrimaryKeyRelatedField(
        queryset=Supplier.objects, required=False, allow_null=True
    )
    supplier_invoice = serializers.CharField(max_length=40, required=False, allow_blank=True)
    purchased_at = serializers.DateTimeField(required=False)
    notes = serializers.CharField(required=False, allow_blank=True)
    items = PurchaseItemInputSerializer(many=True)
    receive = serializers.BooleanField(
        default=False,
        help_text="Receive into stock immediately. The common flow for a small store.",
    )

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("A purchase needs at least one item.")
        seen = set()
        for item in value:
            variant_id = str(item["variant"].pk)
            if variant_id in seen:
                raise serializers.ValidationError("Each variant may appear only once per purchase.")
            seen.add(variant_id)
        return value
