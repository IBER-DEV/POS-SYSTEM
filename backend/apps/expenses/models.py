"""Operating expenses: what the business spends that is not merchandise.

Rent, payroll, utilities, the delivery paid out of the drawer. Merchandise is
never an expense here - it enters through a Purchase and leaves as cost of
goods sold when it is actually sold, so counting it twice is impossible by
construction.

An expense paid in cash is not only a record: the money left the drawer, so it
writes a WITHDRAWAL into the cash ledger and the arqueo balances on its own.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.core.enums import PaymentMethod
from apps.core.models import TenantScopedModel


class ExpenseCategory(TenantScopedModel):
    """How the owner groups spending. Editable per business, never global."""

    name = models.CharField(max_length=80)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "expense_categories"
        ordering = ["name"]
        verbose_name_plural = "expense categories"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"], name="uq_expense_category_org_name"
            ),
        ]

    def __str__(self) -> str:
        return self.name


class Expense(TenantScopedModel):
    """One payment out. Always positive; the direction is implicit."""

    category = models.ForeignKey(
        ExpenseCategory, on_delete=models.PROTECT, related_name="expenses"
    )
    location = models.ForeignKey(
        "organizations.Location", on_delete=models.PROTECT, related_name="expenses"
    )
    # Optional: the same supplier that sells merchandise may also invoice a
    # service, and the owner wants both under one name.
    supplier = models.ForeignKey(
        "purchasing.Supplier",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expenses",
    )

    description = models.CharField(max_length=240)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    payment_method = models.CharField(
        max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.CASH
    )
    occurred_at = models.DateTimeField(db_index=True)

    # Set only when the money physically left an open drawer, which is what
    # links this record to the arqueo that will have to account for it.
    cash_session = models.ForeignKey(
        "cash.CashSession",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expenses",
    )

    reference = models.CharField(max_length=80, blank=True, help_text="Invoice or receipt number.")
    note = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="expenses"
    )

    class Meta:
        db_table = "expenses"
        ordering = ["-occurred_at", "-created_at"]
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="ck_expense_amount_positive"),
        ]
        indexes = [
            models.Index(fields=["organization", "-occurred_at"]),
            models.Index(fields=["organization", "category", "-occurred_at"]),
            models.Index(fields=["organization", "location", "-occurred_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.description} {self.amount}"

    @property
    def paid_from_drawer(self) -> bool:
        return self.cash_session_id is not None
