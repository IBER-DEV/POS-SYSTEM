from __future__ import annotations

import django_filters as filters

from .models import Expense, ExpenseCategory

# Relational filters are declared explicitly for the same reason as elsewhere:
# django-filter would otherwise evaluate the related queryset at import time,
# when no tenant context exists.


class ExpenseCategoryFilter(filters.FilterSet):
    class Meta:
        model = ExpenseCategory
        fields = ["is_active"]


class ExpenseFilter(filters.FilterSet):
    category = filters.UUIDFilter(field_name="category_id")
    location = filters.UUIDFilter(field_name="location_id")
    supplier = filters.UUIDFilter(field_name="supplier_id")
    cash_session = filters.UUIDFilter(field_name="cash_session_id")
    occurred_from = filters.IsoDateTimeFilter(field_name="occurred_at", lookup_expr="gte")
    occurred_to = filters.IsoDateTimeFilter(field_name="occurred_at", lookup_expr="lte")
    min_amount = filters.NumberFilter(field_name="amount", lookup_expr="gte")

    class Meta:
        model = Expense
        fields = ["payment_method"]
