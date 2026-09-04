"""Expenses: money out that is not merchandise, and the drawer it leaves from."""
from __future__ import annotations

from decimal import Decimal

import pytest

from apps.cash.models import CashMovementType, CashSession
from apps.cash.services import CashService
from apps.core.context import tenant_context
from apps.expenses.models import Expense, ExpenseCategory

pytestmark = pytest.mark.django_db

EXPENSES = "/api/v1/expenses/"


@pytest.fixture
def category(tenant_a):
    with tenant_context(tenant_a.org.pk):
        return ExpenseCategory.objects.get(name="Arriendo")


def test_a_new_business_can_record_an_expense_without_setting_anything_up(tenant_a, client_for):
    """Las categorías por defecto se crean con el negocio."""
    names = client_for(tenant_a.owner).get("/api/v1/expense-categories/").data["results"]

    assert {row["name"] for row in names} >= {"Arriendo", "Nómina", "Servicios públicos"}


def test_a_cash_expense_leaves_the_drawer_and_the_arqueo_still_balances(
    tenant_a, category, open_register, client_for
):
    """El caso que justifica todo el módulo: sacar plata del cajón para pagar algo."""
    register, session = open_register(tenant_a, opening_amount="100000.00")
    client = client_for(tenant_a.owner)

    response = client.post(
        EXPENSES,
        {
            "category": str(category.pk),
            "description": "Domicilio de la tarde",
            "amount": "20000.00",
            "payment_method": "CASH",
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    assert response.data["paid_from_drawer"] is True
    assert str(response.data["cash_session"]) == str(session.pk)

    with tenant_context(tenant_a.org.pk):
        movement = session.movements.get(movement_type=CashMovementType.WITHDRAWAL)
        assert movement.amount == Decimal("-20000.00")
        assert movement.source_type == "expense"
        # Lo que el cajón debe tener ya descuenta el gasto: contar 80.000 cuadra.
        assert CashService.expected_amount(session) == Decimal("80000.00")


def test_a_card_expense_never_touches_the_drawer(tenant_a, category, open_register, client_for):
    register, session = open_register(tenant_a, opening_amount="100000.00")
    client = client_for(tenant_a.owner)

    response = client.post(
        EXPENSES,
        {
            "category": str(category.pk),
            "description": "Arriendo de octubre",
            "amount": "1500000.00",
            "payment_method": "TRANSFER",
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.data["paid_from_drawer"] is False
    with tenant_context(tenant_a.org.pk):
        assert not session.movements.filter(movement_type=CashMovementType.WITHDRAWAL).exists()
        assert CashService.expected_amount(session) == Decimal("100000.00")


def test_a_cash_expense_with_no_open_register_is_still_recorded(tenant_a, category, client_for):
    """Lo pagó de su bolsillo: rechazarlo solo sacaría la cifra del sistema."""
    response = client_for(tenant_a.owner).post(
        EXPENSES,
        {
            "category": str(category.pk),
            "description": "Servicios públicos",
            "amount": "180000.00",
            "payment_method": "CASH",
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.data["paid_from_drawer"] is False


def test_two_open_registers_force_the_caller_to_say_which_drawer(
    tenant_a, category, open_register, client_for
):
    open_register(tenant_a, opening_amount="100000.00", code="CAJA1")
    open_register(tenant_a, opening_amount="100000.00", code="CAJA2")
    client = client_for(tenant_a.owner)

    ambiguous = client.post(
        EXPENSES,
        {
            "category": str(category.pk),
            "description": "Domicilio",
            "amount": "10000.00",
            "payment_method": "CASH",
        },
        format="json",
    )

    assert ambiguous.status_code == 400
    assert ambiguous.data["code"] == "invalid_operation"

    with tenant_context(tenant_a.org.pk):
        chosen = CashSession.objects.filter(register__code="CAJA2").get()
    explicit = client.post(
        EXPENSES,
        {
            "category": str(category.pk),
            "description": "Domicilio",
            "amount": "10000.00",
            "payment_method": "CASH",
            "cash_session": str(chosen.pk),
        },
        format="json",
    )

    assert explicit.status_code == 201
    assert str(explicit.data["cash_session"]) == str(chosen.pk)


def test_deleting_an_expense_puts_the_money_back_while_the_shift_is_open(
    tenant_a, category, open_register, client_for
):
    register, session = open_register(tenant_a, opening_amount="100000.00")
    client = client_for(tenant_a.owner)
    expense = client.post(
        EXPENSES,
        {
            "category": str(category.pk),
            "description": "Se digitó mal",
            "amount": "20000.00",
            "payment_method": "CASH",
        },
        format="json",
    ).data

    assert client.delete(f"{EXPENSES}{expense['id']}/").status_code == 204

    with tenant_context(tenant_a.org.pk):
        assert not Expense.objects.filter(pk=expense["id"]).exists()
        assert not session.movements.filter(source_type="expense").exists()
        assert CashService.expected_amount(session) == Decimal("100000.00")


def test_an_expense_inside_a_closed_arqueo_cannot_be_deleted(
    tenant_a, category, open_register, client_for
):
    """Ese número ya lo firmó alguien al cerrar: se corrige con un ajuste."""
    register, session = open_register(tenant_a, opening_amount="100000.00")
    client = client_for(tenant_a.owner)
    expense = client.post(
        EXPENSES,
        {
            "category": str(category.pk),
            "description": "Domicilio",
            "amount": "20000.00",
            "payment_method": "CASH",
        },
        format="json",
    ).data
    with tenant_context(tenant_a.org.pk):
        CashService.close_session(
            session=session, counted_amount="80000.00", user=tenant_a.owner
        )

    response = client.delete(f"{EXPENSES}{expense['id']}/")

    assert response.status_code == 400
    with tenant_context(tenant_a.org.pk):
        assert Expense.objects.filter(pk=expense["id"]).exists()


def test_the_amount_cannot_be_edited_after_the_fact(tenant_a, category, client_for):
    """Cambiarlo reescribiría un movimiento de caja que un arqueo pudo contar."""
    client = client_for(tenant_a.owner)
    expense = client.post(
        EXPENSES,
        {
            "category": str(category.pk),
            "description": "Papelería",
            "amount": "30000.00",
            "payment_method": "CASH",
        },
        format="json",
    ).data

    response = client.patch(
        f"{EXPENSES}{expense['id']}/", {"amount": "999999.00", "note": "corregido"}, format="json"
    )

    assert response.status_code == 200
    with tenant_context(tenant_a.org.pk):
        assert Expense.objects.get(pk=expense["id"]).amount == Decimal("30000.00")


def test_expenses_never_cross_tenants(tenant_a, tenant_b, category, client_for):
    client_for(tenant_a.owner).post(
        EXPENSES,
        {
            "category": str(category.pk),
            "description": "Arriendo",
            "amount": "1000000.00",
            "payment_method": "TRANSFER",
        },
        format="json",
    )

    other = client_for(tenant_b.owner).get(EXPENSES)

    assert other.data["count"] == 0


def test_a_cashier_cannot_see_or_record_expenses(tenant_a, category, make_employee, client_for):
    """Lo que gasta el negocio no es asunto del mostrador."""
    from apps.accounts.models import Membership

    cashier = make_employee(tenant_a, role=Membership.Role.CASHIER)
    client = client_for(cashier)

    assert client.get(EXPENSES).status_code == 403
    assert (
        client.post(
            EXPENSES,
            {
                "category": str(category.pk),
                "description": "X",
                "amount": "1000.00",
                "payment_method": "CASH",
            },
            format="json",
        ).status_code
        == 403
    )


# -- Reportes -------------------------------------------------------------


def test_net_profit_subtracts_the_expenses_from_the_gross_margin(
    tenant_a, category, make_stocked_variant, sell, client_for
):
    """La cifra que el dueño realmente quiere y que antes no existía."""
    variant = make_stocked_variant(tenant_a, quantity=10, price="100000.00", cost="60000.00")
    client = client_for(tenant_a.owner)
    sell(client, [{"variant": str(variant.pk), "quantity": 2}])
    client.post(
        EXPENSES,
        {
            "category": str(category.pk),
            "description": "Arriendo",
            "amount": "50000.00",
            "payment_method": "TRANSFER",
        },
        format="json",
    )

    profit = client.get("/api/v1/reports/profit/").data

    assert Decimal(profit["revenue"]) == Decimal("200000.00")
    assert Decimal(profit["cost_of_goods"]) == Decimal("120000.00")
    assert Decimal(profit["gross_profit"]) == Decimal("80000.00")
    assert Decimal(profit["expenses_total"]) == Decimal("50000.00")
    assert Decimal(profit["net_profit"]) == Decimal("30000.00")


def test_the_expenses_report_groups_by_category(tenant_a, category, client_for):
    client = client_for(tenant_a.owner)
    with tenant_context(tenant_a.org.pk):
        payroll = ExpenseCategory.objects.get(name="Nómina")
    for target, amount in ((category, "1000000.00"), (payroll, "2500000.00"), (payroll, "500000.00")):
        client.post(
            EXPENSES,
            {
                "category": str(target.pk),
                "description": "Pago",
                "amount": amount,
                "payment_method": "TRANSFER",
            },
            format="json",
        )

    report = client.get("/api/v1/reports/expenses/").data

    assert Decimal(report["expenses_total"]) == Decimal("4000000.00")
    # Ordenado por monto: la nómina pesa más que el arriendo.
    assert report["by_category"][0]["name"] == "Nómina"
    assert Decimal(report["by_category"][0]["total"]) == Decimal("3000000.00")
    assert Decimal(report["by_method"]["TRANSFER"]) == Decimal("4000000.00")


def test_the_dashboard_answers_the_whole_page_in_one_request(
    tenant_a, category, make_stocked_variant, sell, client_for
):
    variant = make_stocked_variant(tenant_a, quantity=10, price="100000.00", cost="60000.00")
    client = client_for(tenant_a.owner)
    sell(client, [{"variant": str(variant.pk), "quantity": 3}])
    client.post(
        EXPENSES,
        {
            "category": str(category.pk),
            "description": "Arriendo",
            "amount": "40000.00",
            "payment_method": "TRANSFER",
        },
        format="json",
    )

    body = client.get("/api/v1/reports/dashboard/").data

    assert set(body) == {"period", "sales", "profit", "refunds", "inventory", "top_products"}
    assert body["sales"]["sales_count"] == 1
    assert Decimal(body["profit"]["net_profit"]) == Decimal("80000.00")
    assert body["inventory"]["units_on_hand"] == 7
    assert body["top_products"][0]["units"] == 3
    # Todos los bloques comparten el mismo periodo, que es el punto de pedirlo junto.
    assert body["sales"]["period"] == body["profit"]["period"] == body["period"]


def test_the_dashboard_and_the_separate_reports_agree(
    tenant_a, make_stocked_variant, sell, client_for
):
    """Si el bloque combinado y el detalle difieren, el combinado es una mentira."""
    variant = make_stocked_variant(tenant_a, quantity=10, price="100000.00", cost="60000.00")
    client = client_for(tenant_a.owner)
    sell(client, [{"variant": str(variant.pk), "quantity": 2}])

    dashboard = client.get("/api/v1/reports/dashboard/").data
    sales = client.get("/api/v1/reports/sales-summary/").data
    profit = client.get("/api/v1/reports/profit/").data

    # El periodo se resuelve por petición, así que difiere en milisegundos entre
    # llamadas: justamente la razón de pedir la página en un solo request.
    assert {k: v for k, v in dashboard["sales"].items() if k != "period"} == {
        k: v for k, v in sales.items() if k != "period"
    }
    assert {k: v for k, v in dashboard["profit"].items() if k != "period"} == {
        k: v for k, v in profit.items() if k != "period"
    }
