"""A retried request must not become two operations."""
from __future__ import annotations

import uuid

import pytest

from apps.core.context import tenant_context
from apps.core.json import to_jsonable
from apps.inventory.models import InventoryMovement
from apps.inventory.services import InventoryService

pytestmark = pytest.mark.django_db

ADJUST_URL = "/api/v1/inventory/adjustments/"


def payload(variant, quantity=-3):
    return {"reason": "Merma", "lines": [{"variant": str(variant.pk), "quantity": quantity}]}


def test_same_key_and_payload_runs_once(tenant_a, make_variant, client_for):
    variant = make_variant(tenant_a)
    client = client_for(tenant_a.owner, tenant_a.org)
    client.post(ADJUST_URL, payload(variant, 10), format="json")

    key = str(uuid.uuid4())
    first = client.post(ADJUST_URL, payload(variant), format="json", HTTP_IDEMPOTENCY_KEY=key)
    second = client.post(ADJUST_URL, payload(variant), format="json", HTTP_IDEMPOTENCY_KEY=key)

    assert first.status_code == second.status_code == 201
    # The replay is the stored JSON snapshot, so compare in JSON terms.
    assert to_jsonable(first.data) == to_jsonable(second.data)

    with tenant_context(tenant_a.org.pk):
        assert InventoryService.available(location=tenant_a.location, variant=variant) == 7
        assert InventoryMovement.objects.filter(variant=variant, quantity=-3).count() == 1


def test_same_key_with_a_different_payload_is_rejected(tenant_a, make_variant, client_for):
    variant = make_variant(tenant_a)
    client = client_for(tenant_a.owner, tenant_a.org)
    client.post(ADJUST_URL, payload(variant, 10), format="json")

    key = str(uuid.uuid4())
    client.post(ADJUST_URL, payload(variant, -3), format="json", HTTP_IDEMPOTENCY_KEY=key)
    conflict = client.post(ADJUST_URL, payload(variant, -1), format="json", HTTP_IDEMPOTENCY_KEY=key)

    assert conflict.status_code == 409
    assert conflict.data["code"] == "idempotency_conflict"

    with tenant_context(tenant_a.org.pk):
        assert InventoryService.available(location=tenant_a.location, variant=variant) == 7


def test_a_failed_operation_releases_its_key(tenant_a, make_variant, client_for):
    """A retry after a business failure must be allowed to succeed."""
    variant = make_variant(tenant_a)
    client = client_for(tenant_a.owner, tenant_a.org)
    client.post(ADJUST_URL, payload(variant, 5), format="json")

    key = str(uuid.uuid4())
    failed = client.post(ADJUST_URL, payload(variant, -50), format="json", HTTP_IDEMPOTENCY_KEY=key)
    assert failed.status_code == 409
    assert failed.data["code"] == "insufficient_stock"

    retry = client.post(ADJUST_URL, payload(variant, -2), format="json", HTTP_IDEMPOTENCY_KEY=key)
    assert retry.status_code == 201

    with tenant_context(tenant_a.org.pk):
        assert InventoryService.available(location=tenant_a.location, variant=variant) == 3


def test_keys_are_scoped_per_tenant(tenant_a, tenant_b, make_variant, client_for):
    """Two businesses using the same key by chance must not collide."""
    key = str(uuid.uuid4())

    variant_a = make_variant(tenant_a)
    client_a = client_for(tenant_a.owner, tenant_a.org)
    client_a.post(ADJUST_URL, payload(variant_a, 10), format="json")
    response_a = client_a.post(ADJUST_URL, payload(variant_a, -1), format="json", HTTP_IDEMPOTENCY_KEY=key)

    variant_b = make_variant(tenant_b)
    client_b = client_for(tenant_b.owner, tenant_b.org)
    client_b.post(ADJUST_URL, payload(variant_b, 10), format="json")
    response_b = client_b.post(ADJUST_URL, payload(variant_b, -1), format="json", HTTP_IDEMPOTENCY_KEY=key)

    assert response_a.status_code == 201
    assert response_b.status_code == 201
