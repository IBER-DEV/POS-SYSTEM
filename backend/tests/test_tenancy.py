"""Tenant isolation. If any of these fail, nothing else about the product matters."""
from __future__ import annotations

import pytest

from apps.catalog.models import ProductVariant
from apps.core.context import tenant_context, unscoped
from apps.core.exceptions import TenantContextMissing

pytestmark = pytest.mark.django_db


def test_listing_never_crosses_tenants(tenant_a, tenant_b, make_variant, client_for):
    make_variant(tenant_a, sku="A-001")
    make_variant(tenant_b, sku="B-001")

    response = client_for(tenant_b.owner, tenant_b.org).get("/api/v1/variants/")

    assert response.status_code == 200
    skus = {row["sku"] for row in response.data["results"]}
    assert skus == {"B-001"}


def test_reading_another_tenants_row_by_id_is_404_not_403(
    tenant_a, tenant_b, make_variant, client_for
):
    """404, deliberately: a 403 would confirm the row exists."""
    variant = make_variant(tenant_a)

    response = client_for(tenant_b.owner, tenant_b.org).get(f"/api/v1/variants/{variant.pk}/")

    assert response.status_code == 404


def test_nested_id_from_another_tenant_is_rejected(tenant_a, tenant_b, make_variant, client_for):
    """The classic multi-tenant hole: a foreign id buried in a request body."""
    foreign_variant = make_variant(tenant_a)

    response = client_for(tenant_b.owner, tenant_b.org).post(
        "/api/v1/inventory/adjustments/",
        {"lines": [{"variant": str(foreign_variant.pk), "quantity": 5}]},
        format="json",
    )

    assert response.status_code == 400
    with tenant_context(tenant_a.org.pk):
        assert ProductVariant.objects.get(pk=foreign_variant.pk).stock_levels.count() == 0


def test_writing_another_tenants_row_is_404(tenant_a, tenant_b, make_variant, client_for):
    variant = make_variant(tenant_a, price="100000.00")

    response = client_for(tenant_b.owner, tenant_b.org).patch(
        f"/api/v1/variants/{variant.pk}/", {"price": "1.00"}, format="json"
    )

    assert response.status_code == 404
    variant.refresh_from_db()
    assert str(variant.price) == "100000.00"


def test_query_without_tenant_context_fails_loudly(tenant_a, make_variant):
    """Never an empty queryset: that would hide the bug instead of reporting it."""
    make_variant(tenant_a)

    with pytest.raises(TenantContextMissing):
        list(ProductVariant.objects.all())


def test_unscoped_is_the_only_way_to_cross_tenants(tenant_a, tenant_b, make_variant):
    make_variant(tenant_a)
    make_variant(tenant_b)

    with unscoped():
        assert ProductVariant.objects.count() == 2
