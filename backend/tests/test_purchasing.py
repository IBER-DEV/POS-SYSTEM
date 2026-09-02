"""Purchases are the documented origin of stock."""
from __future__ import annotations

from decimal import Decimal

import pytest

from apps.core.context import tenant_context
from apps.inventory.models import InventoryMovement, MovementType
from apps.inventory.services import InventoryService

pytestmark = pytest.mark.django_db


@pytest.fixture
def supplier(tenant_a, client_for):
    client = client_for(tenant_a.owner, tenant_a.org)
    return client, client.post(
        "/api/v1/suppliers/", {"name": "Distribuidora Andina", "tax_id": "800111222-3"}, format="json"
    ).data


def test_receiving_a_purchase_creates_ledger_movements(tenant_a, make_variant, supplier):
    client, supplier_data = supplier
    variant = make_variant(tenant_a, sku="ZAP-40")

    response = client.post(
        "/api/v1/purchases/",
        {
            "supplier": supplier_data["id"],
            "supplier_invoice": "FV-9001",
            "receive": True,
            "items": [{"variant": str(variant.pk), "quantity": 12, "unit_cost": "60000.00"}],
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    assert response.data["status"] == "RECEIVED"
    assert response.data["number"] == "C-000001"
    assert Decimal(response.data["total_cost"]) == Decimal("720000.00")

    with tenant_context(tenant_a.org.pk):
        assert InventoryService.available(location=tenant_a.location, variant=variant) == 12
        movement = InventoryMovement.objects.get(movement_type=MovementType.PURCHASE)
        assert movement.quantity == 12
        assert movement.unit_cost == Decimal("60000.00")
        assert movement.source_type == "purchase"


def test_a_draft_purchase_does_not_touch_stock(tenant_a, make_variant, supplier):
    client, supplier_data = supplier
    variant = make_variant(tenant_a, sku="ZAP-41")

    response = client.post(
        "/api/v1/purchases/",
        {
            "supplier": supplier_data["id"],
            "items": [{"variant": str(variant.pk), "quantity": 5, "unit_cost": "60000.00"}],
        },
        format="json",
    )

    assert response.data["status"] == "DRAFT"
    assert response.data["number"] == ""  # numbers are only assigned on receipt
    with tenant_context(tenant_a.org.pk):
        assert InventoryService.available(location=tenant_a.location, variant=variant) == 0


def test_a_purchase_cannot_be_received_twice(tenant_a, make_variant, supplier):
    client, supplier_data = supplier
    variant = make_variant(tenant_a, sku="ZAP-42")
    purchase = client.post(
        "/api/v1/purchases/",
        {
            "supplier": supplier_data["id"],
            "items": [{"variant": str(variant.pk), "quantity": 5, "unit_cost": "60000.00"}],
        },
        format="json",
    ).data

    first = client.post(f"/api/v1/purchases/{purchase['id']}/receive/", {}, format="json")
    second = client.post(f"/api/v1/purchases/{purchase['id']}/receive/", {}, format="json")

    assert first.status_code == 200
    assert second.status_code == 400
    with tenant_context(tenant_a.org.pk):
        assert InventoryService.available(location=tenant_a.location, variant=variant) == 5


def test_receiving_updates_the_moving_average_cost(tenant_a, make_variant, supplier):
    """10 @ 100.000 then 10 @ 200.000 averages to 150.000."""
    client, supplier_data = supplier
    variant = make_variant(tenant_a, sku="ZAP-43")

    for cost in ("100000.00", "200000.00"):
        client.post(
            "/api/v1/purchases/",
            {
                "supplier": supplier_data["id"],
                "receive": True,
                "items": [{"variant": str(variant.pk), "quantity": 10, "unit_cost": cost}],
            },
            format="json",
        )

    variant.refresh_from_db()
    assert variant.average_cost == Decimal("150000.00")
    assert variant.last_purchase_cost == Decimal("200000.00")


def test_a_received_purchase_cannot_be_cancelled(tenant_a, make_variant, supplier):
    """The ledger already recorded where that stock came from."""
    client, supplier_data = supplier
    variant = make_variant(tenant_a, sku="ZAP-44")
    purchase = client.post(
        "/api/v1/purchases/",
        {
            "supplier": supplier_data["id"],
            "receive": True,
            "items": [{"variant": str(variant.pk), "quantity": 5, "unit_cost": "60000.00"}],
        },
        format="json",
    ).data

    response = client.post(f"/api/v1/purchases/{purchase['id']}/cancel/", {}, format="json")

    assert response.status_code == 400
    with tenant_context(tenant_a.org.pk):
        assert InventoryService.available(location=tenant_a.location, variant=variant) == 5


def test_a_retried_purchase_is_one_purchase(tenant_a, make_variant, supplier):
    client, supplier_data = supplier
    variant = make_variant(tenant_a, sku="ZAP-45")
    body = {
        "supplier": supplier_data["id"],
        "receive": True,
        "items": [{"variant": str(variant.pk), "quantity": 8, "unit_cost": "60000.00"}],
    }

    first = client.post("/api/v1/purchases/", body, format="json", HTTP_IDEMPOTENCY_KEY="p-1")
    second = client.post("/api/v1/purchases/", body, format="json", HTTP_IDEMPOTENCY_KEY="p-1")

    assert first.data["id"] == second.data["id"]
    with tenant_context(tenant_a.org.pk):
        assert InventoryService.available(location=tenant_a.location, variant=variant) == 8


def test_purchases_never_cross_tenants(tenant_a, tenant_b, make_variant, supplier, client_for):
    client, supplier_data = supplier
    variant_b = make_variant(tenant_b, sku="OTRO-1")

    response = client.post(
        "/api/v1/purchases/",
        {
            "supplier": supplier_data["id"],
            "items": [{"variant": str(variant_b.pk), "quantity": 5, "unit_cost": "10.00"}],
        },
        format="json",
    )

    assert response.status_code == 400
