from __future__ import annotations

from rest_framework import serializers

from apps.core.serializers import TenantModelSerializer

from .models import Customer


class CustomerSerializer(TenantModelSerializer):
    total_purchases = serializers.IntegerField(read_only=True)
    total_spent = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = Customer
        fields = [
            "id",
            "name",
            "phone",
            "email",
            "document_type",
            "document_number",
            "address",
            "birth_date",
            "notes",
            "is_active",
            "total_purchases",
            "total_spent",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]
