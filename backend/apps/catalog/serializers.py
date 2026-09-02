from __future__ import annotations

from django.db import transaction
from rest_framework import serializers

from apps.core.serializers import TenantModelSerializer

from .models import Brand, Category, Product, ProductVariant


class CategorySerializer(TenantModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "parent", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]


class BrandSerializer(TenantModelSerializer):
    class Meta:
        model = Brand
        fields = ["id", "name", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]


class ProductVariantSerializer(TenantModelSerializer):
    display_name = serializers.CharField(read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    tax_rate = serializers.DecimalField(
        source="product.tax_rate", max_digits=5, decimal_places=2, read_only=True
    )

    class Meta:
        model = ProductVariant
        fields = [
            "id",
            "product",
            "product_name",
            "display_name",
            "sku",
            "barcode",
            "size",
            "color",
            "attributes",
            "price",
            "average_cost",
            "last_purchase_cost",
            "tax_rate",
            "weight_grams",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "average_cost", "last_purchase_cost", "created_at"]


class NestedVariantSerializer(TenantModelSerializer):
    """Variants written inline when creating a product."""

    id = serializers.UUIDField(required=False)

    class Meta:
        model = ProductVariant
        fields = [
            "id",
            "sku",
            "barcode",
            "size",
            "color",
            "attributes",
            "price",
            "weight_grams",
            "is_active",
        ]


class ProductSerializer(TenantModelSerializer):
    variants = NestedVariantSerializer(many=True, required=False)
    category_name = serializers.CharField(source="category.name", read_only=True, default=None)
    brand_name = serializers.CharField(source="brand.name", read_only=True, default=None)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "description",
            "category",
            "category_name",
            "brand",
            "brand_name",
            "tax_rate",
            "track_inventory",
            "is_active",
            "variants",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate_variants(self, value):
        skus = [v["sku"] for v in value if v.get("sku")]
        if len(skus) != len(set(skus)):
            raise serializers.ValidationError("Duplicate SKU in the submitted variants.")
        return value

    @transaction.atomic
    def create(self, validated_data):
        variants = validated_data.pop("variants", [])
        product = super().create(validated_data)
        ProductVariant.objects.bulk_create(
            [
                ProductVariant(organization=product.organization, product=product, **variant)
                for variant in variants
            ]
        )
        return product

    @transaction.atomic
    def update(self, instance, validated_data):
        """Upsert semantics: variants with an id are updated, new ones created.

        Variants are never deleted here - they are referenced by inventory
        movements and sales. Deactivate instead.
        """
        variants = validated_data.pop("variants", None)
        product = super().update(instance, validated_data)
        if variants is None:
            return product

        existing = {str(v.pk): v for v in product.variants.all()}
        for payload in variants:
            variant_id = str(payload.pop("id", "") or "")
            if variant_id and variant_id in existing:
                variant = existing[variant_id]
                for field, value in payload.items():
                    setattr(variant, field, value)
                variant.save()
            else:
                ProductVariant.objects.create(
                    organization=product.organization, product=product, **payload
                )
        return product
