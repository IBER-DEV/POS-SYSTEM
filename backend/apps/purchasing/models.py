"""Suppliers and purchases.

A purchase is the documented origin of stock. Receiving it writes PURCHASE
movements through InventoryService and updates the moving average cost, so the
question "where did these units come from and what did they cost?" always has
an answer in the ledger.
"""
from __future__ import annotations

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import TenantScopedModel


class Supplier(TenantScopedModel):
    name = models.CharField(max_length=140)
    tax_id = models.CharField(max_length=40, blank=True)
    contact_name = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "suppliers"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "name"], name="uq_supplier_org_name"),
        ]

    def __str__(self) -> str:
        return self.name


class Purchase(TenantScopedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        RECEIVED = "RECEIVED", "Received"
        CANCELLED = "CANCELLED", "Cancelled"

    number = models.CharField(max_length=20, blank=True, default="")
    location = models.ForeignKey(
        "organizations.Location", on_delete=models.PROTECT, related_name="purchases"
    )
    supplier = models.ForeignKey(
        Supplier, on_delete=models.PROTECT, related_name="purchases", null=True, blank=True
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)

    supplier_invoice = models.CharField(max_length=40, blank=True)
    purchased_at = models.DateTimeField()
    received_at = models.DateTimeField(null=True, blank=True)

    total_cost = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    notes = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="purchases"
    )
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="received_purchases",
    )

    class Meta:
        db_table = "purchases"
        ordering = ["-purchased_at", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "number"],
                condition=~models.Q(number=""),
                name="uq_purchase_org_number",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "status", "-purchased_at"]),
            models.Index(fields=["organization", "supplier", "-purchased_at"]),
        ]

    def __str__(self) -> str:
        return self.number or f"draft purchase {self.pk}"


class PurchaseItem(TenantScopedModel):
    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name="items")
    variant = models.ForeignKey(
        "catalog.ProductVariant", on_delete=models.PROTECT, related_name="purchase_items"
    )
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_cost = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(0)])
    total_cost = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        db_table = "purchase_items"
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["purchase", "variant"], name="uq_purchase_item_variant"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.quantity} x {self.variant_id}"

# Module-level alias so drf-spectacular can name this enum in the OpenAPI
# schema; its override loader cannot traverse into a nested class.
PURCHASE_STATUS_CHOICES = Purchase.Status.choices
