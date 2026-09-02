from __future__ import annotations

from rest_framework import serializers

from apps.core.serializers import TenantModelSerializer

from .models import Location, Organization


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = [
            "id",
            "name",
            "slug",
            "legal_name",
            "tax_id",
            "country",
            "currency",
            "currency_decimals",
            "timezone",
            "prices_include_tax",
            "default_tax_rate",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "slug", "is_active", "created_at"]


class LocationSerializer(TenantModelSerializer):
    class Meta:
        model = Location
        fields = ["id", "name", "code", "address", "phone", "is_default", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]
