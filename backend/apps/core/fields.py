from __future__ import annotations

from rest_framework import serializers

from .context import get_current_organization_id


class TenantPrimaryKeyRelatedField(serializers.PrimaryKeyRelatedField):
    """Relation field restricted to the current tenant.

    This closes the most common multi-tenant hole: list endpoints are usually
    filtered correctly, but a nested id in a request body (customer_id,
    variant_id, location_id) silently reaches across tenants unless the
    relation queryset is scoped too.
    """

    def get_queryset(self):
        queryset = super().get_queryset()
        organization_id = get_current_organization_id()
        if organization_id is None:
            return queryset.none()
        if "organization" not in {f.name for f in queryset.model._meta.get_fields()}:
            return queryset
        return queryset.filter(organization_id=organization_id)
