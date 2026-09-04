from __future__ import annotations

from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.response import Response

from apps.core import capabilities as caps
from apps.core.views import TenantModelViewSet, TenantViewSetMixin
from apps.organizations.selectors import default_location

from . import services
from .filters import ExpenseCategoryFilter, ExpenseFilter
from .models import Expense, ExpenseCategory
from .serializers import (
    ExpenseCategorySerializer,
    ExpenseCreateSerializer,
    ExpenseSerializer,
    ExpenseUpdateSerializer,
)


class ExpenseCategoryViewSet(TenantModelViewSet):
    serializer_class = ExpenseCategorySerializer
    model = ExpenseCategory
    read_capability = caps.EXPENSES_READ
    write_capability = caps.EXPENSES_WRITE
    filterset_class = ExpenseCategoryFilter
    search_fields = ["name"]

    def perform_destroy(self, instance):
        # Expenses point here with PROTECT: deactivating keeps old reports readable.
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])


class ExpenseViewSet(
    TenantViewSetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Money out that is not merchandise.

    Creating goes through the service, not the serializer, because a cash
    expense also has to leave the drawer - and both writes belong to the same
    transaction.
    """

    serializer_class = ExpenseSerializer
    model = Expense
    select_related = ("category", "location", "supplier", "cash_session", "created_by")
    read_capability = caps.EXPENSES_READ
    write_capability = caps.EXPENSES_WRITE
    filterset_class = ExpenseFilter
    search_fields = ["description", "reference", "note", "supplier__name"]
    ordering_fields = ["occurred_at", "amount", "created_at"]

    def get_serializer_class(self):
        if self.action in ("update", "partial_update"):
            return ExpenseUpdateSerializer
        return ExpenseSerializer

    @extend_schema(request=ExpenseCreateSerializer, responses={201: ExpenseSerializer})
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = ExpenseCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        location = data.get("location") or default_location()
        if location is None:
            return Response(
                {"detail": "This organization has no active location.", "code": "no_location"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        expense = services.record_expense(
            organization=request.organization,
            category=data["category"],
            location=location,
            amount=data["amount"],
            payment_method=data["payment_method"],
            occurred_at=data.get("occurred_at"),
            cash_session=data.get("cash_session"),
            user=request.user,
            supplier=data.get("supplier"),
            description=data["description"],
            reference=data.get("reference", ""),
            note=data.get("note", ""),
        )

        expense = self.get_queryset().get(pk=expense.pk)
        return Response(ExpenseSerializer(expense).data, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance):
        services.delete_expense(expense=instance, user=self.request.user)
