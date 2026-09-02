"""A subscription controls writing, never reading."""
from __future__ import annotations

import pytest

from apps.core.context import tenant_context
from apps.subscriptions.models import Subscription

pytestmark = pytest.mark.django_db


def set_status(tenant, status):
    with tenant_context(tenant.org.pk):
        Subscription.objects.filter(organization=tenant.org).update(status=status)


def test_a_cancelled_subscription_blocks_writes_but_not_reads(
    tenant_a, make_variant, client_for
):
    """A store that stops paying must still be able to get its own data out."""
    make_variant(tenant_a)
    client = client_for(tenant_a.owner, tenant_a.org)
    set_status(tenant_a, Subscription.Status.CANCELLED)

    assert client.get("/api/v1/products/").status_code == 200

    write = client.post("/api/v1/products/", {"name": "Nuevo"}, format="json")
    assert write.status_code == 402
    assert write.data["code"] == "subscription_inactive"


def test_a_trial_and_a_past_due_subscription_keep_working(tenant_a, client_for):
    """Cutting a shop off mid-sale over billing is a decision nobody has made."""
    client = client_for(tenant_a.owner, tenant_a.org)

    assert client.post("/api/v1/brands/", {"name": "Marca A"}, format="json").status_code == 201

    set_status(tenant_a, Subscription.Status.PAST_DUE)
    assert client.post("/api/v1/brands/", {"name": "Marca B"}, format="json").status_code == 201


def test_an_expired_trial_blocks_writes(tenant_a, client_for):
    from datetime import timedelta

    from django.utils import timezone

    client = client_for(tenant_a.owner, tenant_a.org)
    with tenant_context(tenant_a.org.pk):
        Subscription.objects.filter(organization=tenant_a.org).update(
            trial_ends_at=timezone.now() - timedelta(days=1)
        )

    response = client.post("/api/v1/brands/", {"name": "Marca C"}, format="json")

    assert response.status_code == 402
    assert client.get("/api/v1/brands/").status_code == 200
