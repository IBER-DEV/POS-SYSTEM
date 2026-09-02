"""Managers that make tenant isolation the default, not an opt-in.

Design note
-----------
The filter is applied when the queryset is *built*, which is the natural place.
But third-party code (django-filter, drf-spectacular, the admin) introspects
`Model._default_manager.all()` at import time, long before any request exists.
Raising there would make the whole ecosystem unusable.

So a queryset built without a tenant context is not filtered and not rejected -
it is marked *pending* and refuses to execute. Introspection, which only reads
`.query`, keeps working; any attempt to actually read or write data without a
tenant fails loudly. An empty queryset is never returned silently, because that
turns a missing-context bug into mysterious missing data.
"""
from __future__ import annotations

from django.db import models

from .context import get_current_organization_id, is_unscoped
from .exceptions import TenantContextMissing


class TenantQuerySet(models.QuerySet):
    _tenant_pending = False

    def _clone(self):
        clone = super()._clone()
        clone._tenant_pending = self._tenant_pending
        return clone

    def mark_tenant_pending(self):
        clone = self._chain()
        clone._tenant_pending = True
        return clone

    def _require_tenant(self):
        if self._tenant_pending and not is_unscoped():
            raise TenantContextMissing(
                f"{self.model.__name__} was accessed without an active organization. "
                "Wrap the call in apps.core.context.tenant_context(org), or in "
                "unscoped() if crossing tenants is genuinely intended."
            )

    def for_organization(self, organization):
        clone = self.filter(organization_id=getattr(organization, "pk", organization))
        clone._tenant_pending = False
        return clone

    # --- execution points -------------------------------------------------
    def _fetch_all(self):
        self._require_tenant()
        super()._fetch_all()

    def iterator(self, *args, **kwargs):
        self._require_tenant()
        return super().iterator(*args, **kwargs)

    def count(self):
        self._require_tenant()
        return super().count()

    def exists(self):
        self._require_tenant()
        return super().exists()

    def aggregate(self, *args, **kwargs):
        self._require_tenant()
        return super().aggregate(*args, **kwargs)

    def update(self, **kwargs):
        self._require_tenant()
        return super().update(**kwargs)

    def delete(self):
        self._require_tenant()
        return super().delete()

    def create(self, **kwargs):
        self._require_tenant()
        return super().create(**kwargs)

    def bulk_create(self, *args, **kwargs):
        self._require_tenant()
        return super().bulk_create(*args, **kwargs)

    def bulk_update(self, *args, **kwargs):
        self._require_tenant()
        return super().bulk_update(*args, **kwargs)


class TenantManager(models.Manager.from_queryset(TenantQuerySet)):
    """Default manager for every tenant-owned model."""

    def get_queryset(self):
        queryset = super().get_queryset()
        if is_unscoped():
            return queryset
        organization_id = get_current_organization_id()
        if organization_id is None:
            return queryset.mark_tenant_pending()
        return queryset.filter(organization_id=organization_id)
