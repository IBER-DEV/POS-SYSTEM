"""CashService - opening, movements and arqueo."""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.core.audit import record_audit
from apps.core.exceptions import InvalidOperation
from apps.core.money import money

from .models import CashMovement, CashMovementType, CashRegister, CashSession


class CashService:
    @staticmethod
    @transaction.atomic
    def open_session(
        *, organization, register: CashRegister, user, opening_amount=0, notes=""
    ) -> CashSession:
        if not register.is_active:
            raise InvalidOperation("This register is inactive.", register=str(register.pk))

        # The partial unique index is the real guard; this check turns a
        # database error into a readable one.
        if CashSession.objects.filter(register=register, status=CashSession.Status.OPEN).exists():
            raise InvalidOperation(
                "This register already has an open session. Close it before opening another.",
                register=str(register.pk),
            )

        opened_at = timezone.now()
        session = CashSession.objects.create(
            organization=organization,
            register=register,
            opened_by=user,
            opened_at=opened_at,
            opening_amount=money(opening_amount),
            notes=notes,
        )
        if session.opening_amount:
            CashService.record_movement(
                session=session,
                movement_type=CashMovementType.OPENING,
                amount=session.opening_amount,
                user=user,
                note="Base inicial",
            )

        record_audit(
            organization=organization,
            action="cash.opened",
            actor=user,
            obj=session,
            metadata={"register": register.code, "opening_amount": str(session.opening_amount)},
        )
        return session

    @staticmethod
    def record_movement(
        *,
        session: CashSession,
        movement_type: str,
        amount,
        user=None,
        source_type: str = "",
        source_id: str = "",
        note: str = "",
    ) -> CashMovement:
        if not session.is_open:
            raise InvalidOperation("The cash session is closed.", session=str(session.pk))
        amount = money(amount)
        if amount == 0:
            raise InvalidOperation("A cash movement cannot be zero.")

        return CashMovement.objects.create(
            organization=session.organization,
            session=session,
            movement_type=movement_type,
            amount=amount,
            source_type=source_type,
            source_id=str(source_id),
            created_by=user,
            note=note,
        )

    @staticmethod
    def expected_amount(session: CashSession) -> Decimal:
        """What the drawer should hold: the sum of its movements."""
        total = session.movements.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        return money(total)

    @staticmethod
    @transaction.atomic
    def close_session(*, session: CashSession, counted_amount, user, notes: str = "") -> CashSession:
        """Arqueo: compare what was counted against what the movements imply."""
        locked = CashSession.objects.select_for_update().get(pk=session.pk)
        if not locked.is_open:
            raise InvalidOperation("This session is already closed.", session=str(locked.pk))

        expected = CashService.expected_amount(locked)
        counted = money(counted_amount)

        locked.status = CashSession.Status.CLOSED
        locked.closed_by = user
        locked.closed_at = timezone.now()
        locked.expected_amount = expected
        locked.counted_amount = counted
        # Positive means surplus in the drawer, negative means shortfall.
        locked.difference = money(counted - expected)
        if notes:
            locked.notes = f"{locked.notes}\n{notes}".strip()
        locked.save(
            update_fields=[
                "status",
                "closed_by",
                "closed_at",
                "expected_amount",
                "counted_amount",
                "difference",
                "notes",
                "updated_at",
            ]
        )

        record_audit(
            organization=locked.organization,
            action="cash.closed",
            actor=user,
            obj=locked,
            metadata={
                "expected": str(expected),
                "counted": str(counted),
                "difference": str(locked.difference),
            },
        )
        return locked

    @staticmethod
    def session_summary(session: CashSession) -> dict:
        """Everything the closing screen needs, including non-cash totals."""
        from apps.sales.models import Payment, Sale

        by_type = {
            row["movement_type"]: money(row["total"])
            for row in session.movements.values("movement_type").annotate(total=Sum("amount"))
        }
        by_method = {
            row["method"]: money(row["total"])
            for row in Payment.objects.filter(sale__cash_session=session)
            .values("method")
            .annotate(total=Sum("amount"))
        }
        sales = Sale.objects.filter(cash_session=session, status__in=Sale.SETTLED_STATUSES)

        return {
            "expected_amount": CashService.expected_amount(session),
            "opening_amount": session.opening_amount,
            "movements_by_type": by_type,
            "payments_by_method": by_method,
            "sales_count": sales.count(),
            "sales_total": money(sales.aggregate(total=Sum("total"))["total"] or 0),
        }
