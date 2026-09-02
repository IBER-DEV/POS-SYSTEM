from __future__ import annotations

from rest_framework import serializers

from .fields import TenantPrimaryKeyRelatedField


class TenantModelSerializer(serializers.ModelSerializer):
    """Base serializer for tenant-owned models.

    Overriding `serializer_related_field` makes every auto-generated relation
    tenant-scoped, so isolation does not depend on each developer remembering
    to scope a nested id by hand. `organization` is never writable: it comes
    from the authenticated context.
    """

    serializer_related_field = TenantPrimaryKeyRelatedField

    def create(self, validated_data):
        validated_data.pop("organization", None)
        validated_data["organization"] = self.context["request"].organization
        return super().create(validated_data)
