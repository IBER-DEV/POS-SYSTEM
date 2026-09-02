"""The inventory invariant: stock is whatever the ledger says it is."""
from __future__ import annotations

from decimal import Decimal

import pytest

from apps.core.context import tenant_context
from apps.core.exceptions import InsufficientStock
from apps.inventory.models import MovementType, StockDiscrepancy, StockLevel
from apps.inventory.services import InventoryService, MovementLine

pytestmark = pytest.mark.django_db


def apply(tenant, variant, quantity, movement_type=MovementType.ADJUSTMENT, **kwargs):
    return InventoryService.apply_movements(
        organization=tenant.org,
        location=tenant.location,
        lines=[MovementLine(variant_id=str(variant.pk), quantity=quantity)],
        movement_type=movement_type,
        **kwargs,
    )


def test_purchase_then_sale_leaves_the_right_balance(tenant_a, make_variant):
    variant = make_variant(tenant_a)

    with tenant_context(tenant_a.org.pk):
        apply(tenant_a, variant, 10, MovementType.PURCHASE)
        apply(tenant_a, variant, -3, MovementType.SALE)

        assert InventoryService.available(location=tenant_a.location, variant=variant) == 7
        # The materialised balance and the ledger must agree, always.
        assert InventoryService.ledger_balance(location=tenant_a.location, variant=variant) == 7


def test_online_operations_refuse_to_oversell(tenant_a, make_variant):
    variant = make_variant(tenant_a)

    with tenant_context(tenant_a.org.pk):
        apply(tenant_a, variant, 2, MovementType.PURCHASE)

        with pytest.raises(InsufficientStock):
            apply(tenant_a, variant, -5, MovementType.SALE)

        # The rejected operation left nothing behind.
        assert InventoryService.available(location=tenant_a.location, variant=variant) == 2
        assert InventoryService.ledger_balance(location=tenant_a.location, variant=variant) == 2


def test_offline_replay_accepts_negative_stock_and_opens_a_discrepancy(tenant_a, make_variant):
    """Decision D4: the goods already left the shelf, so the fact is recorded."""
    variant = make_variant(tenant_a)

    with tenant_context(tenant_a.org.pk):
        apply(tenant_a, variant, 2, MovementType.PURCHASE)
        apply(
            tenant_a,
            variant,
            -5,
            MovementType.SALE,
            allow_negative=True,
            source_type="sync",
            source_id="op-123",
        )

        assert InventoryService.available(location=tenant_a.location, variant=variant) == -3
        discrepancy = StockDiscrepancy.objects.get(variant=variant)
        assert (discrepancy.quantity_before, discrepancy.quantity_after) == (2, -3)
        assert discrepancy.is_resolved is False


def test_recalculate_rebuilds_stock_from_the_ledger(tenant_a, make_variant):
    variant = make_variant(tenant_a)

    with tenant_context(tenant_a.org.pk):
        apply(tenant_a, variant, 10, MovementType.PURCHASE)
        apply(tenant_a, variant, -4, MovementType.SALE)

        # Simulate drift: something wrote the cache directly, which is a bug.
        StockLevel.objects.filter(variant=variant).update(quantity=999)

        result = InventoryService.recalculate(organization=tenant_a.org)

        assert result["levels_corrected"] == 1
        assert InventoryService.available(location=tenant_a.location, variant=variant) == 6


def test_moving_average_cost_follows_the_purchases(tenant_a, make_variant):
    """Decision D3: 10 @ 100 then 10 @ 200 averages to 150."""
    variant = make_variant(tenant_a)

    with tenant_context(tenant_a.org.pk):
        apply(tenant_a, variant, 10, MovementType.PURCHASE)
        InventoryService.update_average_cost(
            variant=variant, incoming_quantity=10, unit_cost=Decimal("100.00")
        )
        apply(tenant_a, variant, 10, MovementType.PURCHASE)
        InventoryService.update_average_cost(
            variant=variant, incoming_quantity=10, unit_cost=Decimal("200.00")
        )

    variant.refresh_from_db()
    assert variant.average_cost == Decimal("150.00")
    assert variant.last_purchase_cost == Decimal("200.00")


def test_stock_quantity_is_not_writable_through_the_api(tenant_a, make_variant, client_for):
    variant = make_variant(tenant_a)
    with tenant_context(tenant_a.org.pk):
        apply(tenant_a, variant, 10, MovementType.PURCHASE)
        level = StockLevel.objects.get(variant=variant)

    response = client_for(tenant_a.owner, tenant_a.org).patch(
        f"/api/v1/inventory/stock/{level.pk}/",
        {"quantity": 500, "reorder_point": 3},
        format="json",
    )

    assert response.status_code == 200
    level.refresh_from_db()
    assert level.quantity == 10  # ignored: stock only moves through movements
    assert level.reorder_point == 3
