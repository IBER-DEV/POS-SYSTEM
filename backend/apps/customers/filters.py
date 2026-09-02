from __future__ import annotations

import django_filters as filters

from .models import Customer


class CustomerFilter(filters.FilterSet):
    class Meta:
        model = Customer
        fields = ["is_active", "document_type"]
