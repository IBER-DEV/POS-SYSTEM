"""Products and variants: a SKU/barcode is unique across the business, not per product."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db

PRODUCTS = "/api/v1/products/"


def _body(name, variants):
    return {"name": name, "variants": variants}


def test_two_products_cannot_reuse_the_same_sku(tenant_a, client_for):
    """The exact collision reported in production: two products, one generated SKU."""
    client = client_for(tenant_a.owner)
    first = client.post(
        PRODUCTS,
        _body("Zapatillas nike", [{"sku": "ZAP-ZAPA-AZU-43", "price": "50000"}]),
        format="json",
    )
    assert first.status_code == 201

    second = client.post(
        PRODUCTS,
        _body("Zapatos adidas", [{"sku": "ZAP-ZAPA-AZU-43", "price": "50000"}]),
        format="json",
    )

    # A readable 400, never a raw IntegrityError/500.
    assert second.status_code == 400
    assert "ZAP-ZAPA-AZU-43" in str(second.data["variants"])


def test_two_products_cannot_reuse_the_same_barcode(tenant_a, client_for):
    client = client_for(tenant_a.owner)
    client.post(
        PRODUCTS,
        _body("Camiseta", [{"sku": "CAM-1", "barcode": "7701234567890", "price": "30000"}]),
        format="json",
    )

    response = client.post(
        PRODUCTS,
        _body("Otra camiseta", [{"sku": "CAM-2", "barcode": "7701234567890", "price": "30000"}]),
        format="json",
    )

    assert response.status_code == 400
    assert "7701234567890" in str(response.data["variants"])


def test_duplicate_sku_within_the_same_request_is_still_rejected(tenant_a, client_for):
    response = client_for(tenant_a.owner).post(
        PRODUCTS,
        _body(
            "Producto",
            [
                {"sku": "DUP-1", "price": "10000"},
                {"sku": "DUP-1", "price": "10000"},
            ],
        ),
        format="json",
    )

    assert response.status_code == 400


def test_a_product_keeps_its_own_sku_when_edited(tenant_a, client_for):
    """Updating a product must not flag its own variant's SKU as taken."""
    client = client_for(tenant_a.owner)
    created = client.post(
        PRODUCTS, _body("Buso", [{"sku": "BUS-1", "price": "80000"}]), format="json"
    ).data
    variant_id = created["variants"][0]["id"]

    response = client.patch(
        f"{PRODUCTS}{created['id']}/",
        {"variants": [{"id": variant_id, "sku": "BUS-1", "price": "85000"}]},
        format="json",
    )

    assert response.status_code == 200


def test_a_sku_taken_by_another_product_cannot_be_reused_when_editing(tenant_a, client_for):
    client = client_for(tenant_a.owner)
    client.post(PRODUCTS, _body("Producto A", [{"sku": "A-1", "price": "1000"}]), format="json")
    other = client.post(
        PRODUCTS, _body("Producto B", [{"sku": "B-1", "price": "1000"}]), format="json"
    ).data

    response = client.patch(
        f"{PRODUCTS}{other['id']}/",
        {"variants": [{"id": other["variants"][0]["id"], "sku": "A-1", "price": "1000"}]},
        format="json",
    )

    assert response.status_code == 400


def test_the_sku_conflict_is_scoped_to_the_business(tenant_a, tenant_b, client_for):
    """The same SKU is free in an unrelated business."""
    client_for(tenant_a.owner).post(
        PRODUCTS, _body("Producto", [{"sku": "SAME-SKU", "price": "1000"}]), format="json"
    )

    response = client_for(tenant_b.owner).post(
        PRODUCTS, _body("Producto", [{"sku": "SAME-SKU", "price": "1000"}]), format="json"
    )

    assert response.status_code == 201


def test_a_product_can_be_created_without_a_brand(tenant_a, client_for):
    response = client_for(tenant_a.owner).post(
        PRODUCTS, {"name": "Camiseta básica", "variants": []}, format="json"
    )

    assert response.status_code == 201, response.data
    assert response.data["brand"] is None
