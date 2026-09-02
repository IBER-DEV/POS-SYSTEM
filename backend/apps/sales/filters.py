from __future__ import annotations

import django_filters as filters

from .models import Refund, Sale


class SaleFilter(filters.FilterSet):
    location = filters.UUIDFilter(field_name="location_id")
    customer = filters.UUIDFilter(field_name="customer_id")
    seller = filters.UUIDFilter(field_name="seller_id")
    cash_session = filters.UUIDFilter(field_name="cash_session_id")
    occurred_after = filters.IsoDateTimeFilter(field_name="occurred_at", lookup_expr="gte")
    occurred_before = filters.IsoDateTimeFilter(field_name="occurred_at", lookup_expr="lte")

    class Meta:
        model = Sale
        fields = ["status", "source"]


class RefundFilter(filters.FilterSet):
    sale = filters.UUIDFilter(field_name="sale_id")
    location = filters.UUIDFilter(field_name="location_id")
    occurred_after = filters.IsoDateTimeFilter(field_name="occurred_at", lookup_expr="gte")
    occurred_before = filters.IsoDateTimeFilter(field_name="occurred_at", lookup_expr="lte")

    class Meta:
        model = Refund
        fields = ["method", "restock"]
