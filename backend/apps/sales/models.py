"""Sales, payments and refunds.

A completed sale is one transactional fact: the document, its items, its
payments, the stock movements and the cash movement all commit together or none
of them do. There is no state in which a receipt exists but the stock never
left, or the stock left but no receipt exists.

Money is stored tax-inclusive (decision D1). Every line freezes its tax rate and
its unit cost, so a past sale's tax breakdown and margin never change when the
product is edited later.
"""
from __future__ import annotations

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from apps.core.enums import PaymentMethod
from apps.core.models import TenantScopedModel


class Sale(TenantScopedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"
        REFUNDED = "REFUNDED", "Refunded"
        PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED", "Partially refunded"

    class Source(models.TextChoices):
        POS = "POS", "Point of sale"
        SYNC = "SYNC", "Synced from an offline terminal"

    # Statuses in which the sale counts as revenue: cancelled sales never do,
    # refunded ones still happened and are netted by their refunds.
    SETTLED_STATUSES = ("COMPLETED", "PARTIALLY_REFUNDED", "REFUNDED")

    number = models.CharField(max_length=20, blank=True, default="")
    location = models.ForeignKey(
        "organizations.Location", on_delete=models.PROTECT, related_name="sales"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)

    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sales",
    )
    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="sales"
    )
    cash_session = models.ForeignKey(
        "cash.CashSession",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sales",
    )

    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    discount_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    paid_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    change_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    refunded_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    source = models.CharField(max_length=10, choices=Source.choices, default=Source.POS)
    device_id = models.CharField(max_length=64, blank=True, help_text="Terminal that created it offline.")
    # When it happened in the store, which may predate the moment it synced.
    occurred_at = models.DateTimeField(db_index=True)
    notes = models.TextField(blank=True)

    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cancelled_sales",
    )
    cancellation_reason = models.CharField(max_length=240, blank=True)

    class Meta:
        db_table = "sales"
        ordering = ["-occurred_at", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "number"],
                condition=~models.Q(number=""),
                name="uq_sale_org_number",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "status", "-occurred_at"]),
            models.Index(fields=["organization", "location", "-occurred_at"]),
            models.Index(fields=["organization", "customer", "-occurred_at"]),
            models.Index(fields=["organization", "cash_session"]),
        ]

    def __str__(self) -> str:
        return self.number or f"draft sale {self.pk}"

    @property
    def net_total(self):
        """Total minus what has been refunded."""
        return self.total - self.refunded_total


class SaleItem(TenantScopedModel):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items")
    variant = models.ForeignKey(
        "catalog.ProductVariant", on_delete=models.PROTECT, related_name="sale_items"
    )

    # Snapshot of the product at the moment of sale: the receipt must stay
    # readable even after the variant is renamed or deactivated.
    description = models.CharField(max_length=220)
    sku = models.CharField(max_length=64)

    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(max_digits=14, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    line_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    taxable_base = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    # Frozen so margin reports on old sales never move with the average cost.
    unit_cost = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    refunded_quantity = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "sale_items"
        ordering = ["created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(refunded_quantity__lte=models.F("quantity")),
                name="ck_sale_item_refund_within_sold",
            ),
        ]
        indexes = [models.Index(fields=["organization", "variant"])]

    def __str__(self) -> str:
        return f"{self.quantity} x {self.description}"

    @property
    def refundable_quantity(self) -> int:
        return self.quantity - self.refunded_quantity


class Payment(TenantScopedModel):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="payments")
    method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(0)])
    reference = models.CharField(max_length=80, blank=True, help_text="Voucher, approval code.")

    class Meta:
        db_table = "payments"
        ordering = ["created_at"]
        indexes = [models.Index(fields=["organization", "method"])]

    def __str__(self) -> str:
        return f"{self.method} {self.amount}"


class Refund(TenantScopedModel):
    number = models.CharField(max_length=20, blank=True, default="")
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name="refunds")
    location = models.ForeignKey(
        "organizations.Location", on_delete=models.PROTECT, related_name="refunds"
    )
    cash_session = models.ForeignKey(
        "cash.CashSession",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="refunds",
    )
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    method = models.CharField(max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    restock = models.BooleanField(
        default=True, help_text="False when the goods come back damaged and cannot be resold."
    )
    reason = models.CharField(max_length=240, blank=True)
    occurred_at = models.DateTimeField(db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="refunds"
    )

    class Meta:
        db_table = "refunds"
        ordering = ["-occurred_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "number"],
                condition=~models.Q(number=""),
                name="uq_refund_org_number",
            ),
        ]
        indexes = [models.Index(fields=["organization", "-occurred_at"])]

    def __str__(self) -> str:
        return self.number or f"refund {self.pk}"


class RefundItem(TenantScopedModel):
    refund = models.ForeignKey(Refund, on_delete=models.CASCADE, related_name="items")
    sale_item = models.ForeignKey(SaleItem, on_delete=models.PROTECT, related_name="refund_items")
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        db_table = "refund_items"
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.quantity} x {self.sale_item_id}"

# Module-level alias so drf-spectacular can name this enum in the OpenAPI
# schema; its override loader cannot traverse into a nested class.
SALE_STATUS_CHOICES = Sale.Status.choices
