"""Refunds: never more units than were sold, and the money follows the goods."""
from __future__ import annotations

from decimal import Decimal

import pytest

from apps.core.context import tenant_context
from apps.inventory.services import InventoryService
from apps.sales.models import Sale, SaleItem

pytestmark = pytest.mark.django_db

REFUND_URL = "/api/v1/refunds/"


def refund(client, sale_id, lines, key=None, **extra):
    import uuid

    return client.post(
        REFUND_URL,
        {"sale": sale_id, "lines": lines, **extra},
        format="json",
        HTTP_IDEMPOTENCY_KEY=key or str(uuid.uuid4()),
    )


@pytest.fixture
def sold(tenant_a, make_stocked_variant, client_for, sell):
    """A completed sale of 5 units out of 10 in stock."""
    variant = make_stocked_variant(tenant_a, quantity=10, price="119000.00")
    client = client_for(tenant_a.owner, tenant_a.org)
    sale = sell(client, [{"variant": str(variant.pk), "quantity": 5}]).data
    return client, variant, sale


def test_a_partial_refund_restocks_and_marks_the_sale(tenant_a, sold):
    client, variant, sale = sold
    item_id = sale["items"][0]["id"]

    response = refund(client, sale["id"], [{"sale_item": item_id, "quantity": 2}])

    assert response.status_code == 201, response.data
    assert Decimal(response.data["total"]) == Decimal("238000.00")
    assert response.data["number"] == "D-000001"

    detail = client.get(f"/api/v1/sales/{sale['id']}/").data
    assert detail["status"] == "PARTIALLY_REFUNDED"
    assert Decimal(detail["refunded_total"]) == Decimal("238000.00")
    assert detail["items"][0]["refunded_quantity"] == 2
    assert detail["items"][0]["refundable_quantity"] == 3

    with tenant_context(tenant_a.org.pk):
        assert InventoryService.available(location=tenant_a.location, variant=variant) == 7


def test_refunding_everything_marks_the_sale_refunded(tenant_a, sold):
    client, variant, sale = sold
    item_id = sale["items"][0]["id"]

    refund(client, sale["id"], [{"sale_item": item_id, "quantity": 5}])

    detail = client.get(f"/api/v1/sales/{sale['id']}/").data
    assert detail["status"] == "REFUNDED"
    assert Decimal(detail["refunded_total"]) == Decimal(detail["total"])
    with tenant_context(tenant_a.org.pk):
        assert InventoryService.available(location=tenant_a.location, variant=variant) == 10


def test_cannot_refund_more_than_was_sold(tenant_a, sold):
    client, variant, sale = sold
    item_id = sale["items"][0]["id"]

    response = refund(client, sale["id"], [{"sale_item": item_id, "quantity": 6}])

    assert response.status_code == 400
    assert response.data["code"] == "invalid_operation"
    with tenant_context(tenant_a.org.pk):
        assert InventoryService.available(location=tenant_a.location, variant=variant) == 5


def test_successive_refunds_cannot_exceed_the_sold_quantity(tenant_a, sold):
    """Two refunds of 3 against a sale of 5: the second must be refused."""
    client, variant, sale = sold
    item_id = sale["items"][0]["id"]

    first = refund(client, sale["id"], [{"sale_item": item_id, "quantity": 3}])
    second = refund(client, sale["id"], [{"sale_item": item_id, "quantity": 3}])

    assert first.status_code == 201
    assert second.status_code == 400
    assert second.data["context"]["already_refunded"] == 3

    with tenant_context(tenant_a.org.pk):
        assert SaleItem.objects.get(pk=item_id).refunded_quantity == 3
        assert InventoryService.available(location=tenant_a.location, variant=variant) == 8


def test_a_refund_without_restock_does_not_return_the_goods(tenant_a, sold):
    """Damaged merchandise: the customer is paid, the stock is not credited."""
    client, variant, sale = sold
    item_id = sale["items"][0]["id"]

    response = refund(
        client,
        sale["id"],
        [{"sale_item": item_id, "quantity": 2}],
        restock=False,
        reason="Prenda dañada",
    )

    assert response.status_code == 201
    with tenant_context(tenant_a.org.pk):
        assert InventoryService.available(location=tenant_a.location, variant=variant) == 5


def test_a_retried_refund_refunds_once(tenant_a, sold):
    client, variant, sale = sold
    item_id = sale["items"][0]["id"]
    key = "refund-retry"

    first = refund(client, sale["id"], [{"sale_item": item_id, "quantity": 2}], key=key)
    second = refund(client, sale["id"], [{"sale_item": item_id, "quantity": 2}], key=key)

    assert first.status_code == second.status_code == 201
    assert first.data["id"] == second.data["id"]
    with tenant_context(tenant_a.org.pk):
        assert SaleItem.objects.get(pk=item_id).refunded_quantity == 2
        assert InventoryService.available(location=tenant_a.location, variant=variant) == 7


def test_a_cancelled_sale_cannot_be_refunded(tenant_a, sold):
    client, variant, sale = sold
    client.post(f"/api/v1/sales/{sale['id']}/cancel/", {}, format="json")

    response = refund(client, sale["id"], [{"sale_item": sale["items"][0]["id"], "quantity": 1}])

    assert response.status_code == 400
    with tenant_context(tenant_a.org.pk):
        assert InventoryService.available(location=tenant_a.location, variant=variant) == 10


def test_a_sale_with_refunds_cannot_be_cancelled(tenant_a, sold):
    """Cancelling would erase a history the refund already created."""
    client, variant, sale = sold
    refund(client, sale["id"], [{"sale_item": sale["items"][0]["id"], "quantity": 1}])

    response = client.post(f"/api/v1/sales/{sale['id']}/cancel/", {}, format="json")

    assert response.status_code == 400
    assert response.data["code"] == "invalid_operation"
    with tenant_context(tenant_a.org.pk):
        assert Sale.objects.get(pk=sale["id"]).status == Sale.Status.PARTIALLY_REFUNDED


def test_rounding_never_strands_money_on_a_full_refund(
    tenant_a, make_stocked_variant, client_for, sell
):
    """Three units of a price that does not divide by three must still refund in full."""
    variant = make_stocked_variant(tenant_a, quantity=10, price="100000.00")
    client = client_for(tenant_a.owner, tenant_a.org)
    sale = sell(client, [{"variant": str(variant.pk), "quantity": 3}]).data
    item_id = sale["items"][0]["id"]

    refund(client, sale["id"], [{"sale_item": item_id, "quantity": 1}])
    refund(client, sale["id"], [{"sale_item": item_id, "quantity": 2}])

    detail = client.get(f"/api/v1/sales/{sale['id']}/").data
    assert detail["status"] == "REFUNDED"
    assert Decimal(detail["refunded_total"]) == Decimal("300000.00")


def test_refunds_never_cross_tenants(tenant_a, tenant_b, sold, client_for):
    _, _, sale = sold
    client_b = client_for(tenant_b.owner, tenant_b.org)

    response = refund(client_b, sale["id"], [{"sale_item": sale["items"][0]["id"], "quantity": 1}])

    assert response.status_code == 400  # the sale simply does not exist for B
