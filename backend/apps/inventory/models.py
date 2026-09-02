"""Ledger-based inventory.

Source of truth is InventoryMovement, an append-only log. StockLevel is a
materialised cache kept in the same transaction as the movements, so it can
always be rebuilt with `manage.py recalculate_stock`. Nothing in the codebase
is allowed to modify StockLevel outside InventoryService.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.core.models import TenantScopedModel


class MovementType(models.TextChoices):
    INITIAL_STOCK = "INITIAL_STOCK", "Initial stock"
    PURCHASE = "PURCHASE", "Purchase receipt"
    SALE = "SALE", "Sale"
    RETURN = "RETURN", "Customer return"
    ADJUSTMENT = "ADJUSTMENT", "Manual adjustment"
    TRANSFER = "TRANSFER", "Transfer between locations"


class InventoryMovement(TenantScopedModel):
    """One immutable fact: this many units entered or left this location.

    Never updated, never deleted. A mistake is corrected with a compensating
    movement, which is what makes the history auditable.
    """

    location = models.ForeignKey(
        "organizations.Location", on_delete=models.PROTECT, related_name="inventory_movements"
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant", on_delete=models.PROTECT, related_name="inventory_movements"
    )
    quantity = models.IntegerField(help_text="Signed: positive enters stock, negative leaves it.")
    movement_type = models.CharField(max_length=20, choices=MovementType.choices, db_index=True)

    # Unit cost at the moment of the movement. Frozen here so a past sale's
    # margin never changes when the average cost moves later.
    unit_cost = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    # Polymorphic reference to the operation that caused this movement.
    # A plain pair of columns instead of a GenericForeignKey: it keeps the
    # ledger free of joins and content-type lookups on the hot path.
    source_type = models.CharField(max_length=30, blank=True, db_index=True)
    source_id = models.CharField(max_length=64, blank=True, db_index=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_movements",
    )
    occurred_at = models.DateTimeField(
        db_index=True, help_text="When it happened in the store, which may predate sync."
    )
    note = models.CharField(max_length=240, blank=True)

    class Meta:
        db_table = "inventory_movements"
        ordering = ["-occurred_at", "-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(quantity=0), name="ck_inventory_movement_quantity_nonzero"
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "location", "variant", "-occurred_at"]),
            models.Index(fields=["organization", "source_type", "source_id"]),
            models.Index(fields=["organization", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.movement_type} {self.quantity:+d} variant={self.variant_id}"


class StockLevel(TenantScopedModel):
    """Materialised balance per (location, variant). A cache, not the truth."""

    location = models.ForeignKey(
        "organizations.Location", on_delete=models.CASCADE, related_name="stock_levels"
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant", on_delete=models.CASCADE, related_name="stock_levels"
    )
    quantity = models.IntegerField(default=0)
    reorder_point = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "stock_levels"
        constraints = [
            models.UniqueConstraint(
                fields=["location", "variant"], name="uq_stock_level_location_variant"
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "location"]),
            models.Index(fields=["organization", "variant"]),
        ]

    def __str__(self) -> str:
        return f"{self.variant_id}@{self.location_id}={self.quantity}"


class StockDiscrepancy(TenantScopedModel):
    """Raised when a movement drives stock negative.

    Decision D4: online sales refuse to oversell, but an offline sale that
    arrives late is a fact that already happened in the store. It is accepted,
    stock may go negative, and this row asks a human to reconcile.
    """

    location = models.ForeignKey(
        "organizations.Location", on_delete=models.CASCADE, related_name="stock_discrepancies"
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant", on_delete=models.CASCADE, related_name="stock_discrepancies"
    )
    quantity_before = models.IntegerField()
    quantity_requested = models.IntegerField()
    quantity_after = models.IntegerField()
    source_type = models.CharField(max_length=30, blank=True)
    source_id = models.CharField(max_length=64, blank=True)
    reason = models.CharField(max_length=240, blank=True)
    is_resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "stock_discrepancies"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "is_resolved", "-created_at"])]

    def __str__(self) -> str:
        return f"discrepancy variant={self.variant_id} -> {self.quantity_after}"
