from __future__ import annotations

import django_filters as filters

from .models import Purchase, Supplier


class SupplierFilter(filters.FilterSet):
    class Meta:
        model = Supplier
        fields = ["is_active"]


class PurchaseFilter(filters.FilterSet):
    supplier = filters.UUIDFilter(field_name="supplier_id")
    location = filters.UUIDFilter(field_name="location_id")
    purchased_after = filters.IsoDateTimeFilter(field_name="purchased_at", lookup_expr="gte")
    purchased_before = filters.IsoDateTimeFilter(field_name="purchased_at", lookup_expr="lte")

    class Meta:
        model = Purchase
        fields = ["status"]
