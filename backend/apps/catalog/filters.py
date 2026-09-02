from __future__ import annotations

import django_filters as filters

from .models import Category, Product, ProductVariant

# Every filter on a foreign key is declared explicitly. django-filter resolves
# generated relational filters by calling `Model._default_manager.all()` at
# import time, which is exactly when no tenant context exists. Declaring them
# keeps the strict TenantManager strict.


class CategoryFilter(filters.FilterSet):
    parent = filters.UUIDFilter(field_name="parent_id")
    root_only = filters.BooleanFilter(field_name="parent_id", lookup_expr="isnull")

    class Meta:
        model = Category
        fields = ["is_active"]


class ProductFilter(filters.FilterSet):
    category = filters.UUIDFilter(field_name="category_id")
    brand = filters.UUIDFilter(field_name="brand_id")

    class Meta:
        model = Product
        fields = ["is_active"]


class ProductVariantFilter(filters.FilterSet):
    product = filters.UUIDFilter(field_name="product_id")
    category = filters.UUIDFilter(field_name="product__category_id")
    brand = filters.UUIDFilter(field_name="product__brand_id")

    class Meta:
        model = ProductVariant
        fields = ["size", "color", "is_active"]
