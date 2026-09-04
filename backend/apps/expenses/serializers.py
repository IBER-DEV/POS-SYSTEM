from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from apps.cash.models import CashSession
from apps.core.enums import PaymentMethod
from apps.core.fields import TenantPrimaryKeyRelatedField
from apps.core.serializers import TenantModelSerializer
from apps.organizations.models import Location
from apps.purchasing.models import Supplier

from .models import Expense, ExpenseCategory


class ExpenseCategorySerializer(TenantModelSerializer):
    class Meta:
        model = ExpenseCategory
        fields = ["id", "name", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]


class ExpenseSerializer(TenantModelSerializer):
    """How an expense reads back. Written through ExpenseCreateSerializer."""

    category_name = serializers.CharField(source="category.name", read_only=True)
    location_name = serializers.CharField(source="location.name", read_only=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True, default=None)
    paid_from_drawer = serializers.BooleanField(read_only=True)

    class Meta:
        model = Expense
        fields = [
            "id",
            "category",
            "category_name",
            "location",
            "location_name",
            "supplier",
            "supplier_name",
            "description",
            "amount",
            "payment_method",
            "occurred_at",
            "cash_session",
            "paid_from_drawer",
            "reference",
            "note",
            "created_by",
            "created_at",
        ]
        read_only_fields = fields


class ExpenseCreateSerializer(serializers.Serializer):
    category = TenantPrimaryKeyRelatedField(queryset=ExpenseCategory.objects)
    location = TenantPrimaryKeyRelatedField(queryset=Location.objects, required=False)
    supplier = TenantPrimaryKeyRelatedField(
        queryset=Supplier.objects, required=False, allow_null=True
    )
    description = serializers.CharField(max_length=240)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    payment_method = serializers.ChoiceField(
        choices=PaymentMethod.choices, default=PaymentMethod.CASH
    )
    occurred_at = serializers.DateTimeField(required=False)
    cash_session = TenantPrimaryKeyRelatedField(
        queryset=CashSession.objects,
        required=False,
        allow_null=True,
        help_text="Which drawer the cash came out of. Only needed when two tills are open.",
    )
    reference = serializers.CharField(max_length=80, required=False, allow_blank=True)
    note = serializers.CharField(required=False, allow_blank=True)


class ExpenseUpdateSerializer(TenantModelSerializer):
    """Only what can change without moving money.

    The amount and the payment method are not editable: both would have to
    rewrite a drawer movement that an arqueo may already have counted. Delete
    the expense while the shift is open, or correct it with a cash adjustment.
    """

    class Meta:
        model = Expense
        fields = ["category", "supplier", "description", "reference", "note", "occurred_at"]
