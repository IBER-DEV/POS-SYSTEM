"""Aprovisionamiento de negocios."""
from __future__ import annotations

import re

from django.db import transaction

from apps.core.audit import record_audit
from apps.core.context import tenant_context

from .models import Location, Organization

# Con las que arranca cualquier tienda. Son solo un punto de partida: el dueño
# las renombra, desactiva o amplía desde /expense-categories/.
DEFAULT_EXPENSE_CATEGORIES = (
    "Arriendo",
    "Nómina",
    "Servicios públicos",
    "Transporte y domicilios",
    "Aseo y papelería",
    "Publicidad",
    "Mantenimiento",
    "Impuestos y comisiones bancarias",
    "Otros",
)


def derive_username(*, organization, user, preferred: str | None = None) -> str:
    """Un nombre de usuario válido y libre dentro de este negocio.

    El dueño nunca lo escribe al registrarse: se deriva de su correo. Es solo
    la identidad local con la que podrá entrar desde una caja, y puede
    cambiarla después.
    """
    from apps.accounts.models import Membership

    base = preferred or (user.email or "").split("@")[0]
    base = re.sub(r"[^a-z0-9._-]", "", base.strip().lower()).lstrip("._-")
    if len(base) < 3:
        base = f"{base}usuario"[:12] if base else "propietario"

    candidate = base
    suffix = 2
    while Membership.objects.filter(organization=organization, username=candidate).exists():
        candidate = f"{base}{suffix}"
        suffix += 1
    return candidate


@transaction.atomic
def provision_organization(
    *, user, name: str, legal_name: str = "", tax_id: str = "", username: str | None = None
):
    """Crea un negocio con todo lo necesario para usarlo de inmediato.

    Un tenant nunca queda a medio construir: la membresía de dueño, una sede
    por defecto, una caja y una suscripción de prueba se crean en la misma
    transacción que la organización.

    `user` llega ya guardado. Puede ser alguien que acaba de registrarse o
    alguien que ya tiene otros negocios: en ambos casos lo que se crea aquí es
    una membresía más, nunca una cuenta nueva.

    Devuelve la membresía de dueño; la organización está en `.organization`.
    """
    from apps.accounts.models import Membership

    organization = Organization.objects.create(name=name, legal_name=legal_name, tax_id=tax_id)

    # Las escrituras tenant-scoped exigen un contexto activo por diseño.
    with tenant_context(organization.pk):
        location = Location.objects.create(
            organization=organization,
            name="Principal",
            code="PRINCIPAL",
            is_default=True,
        )

        from apps.cash.models import CashRegister

        CashRegister.objects.create(
            organization=organization,
            location=location,
            name="Principal",
            code="PRINCIPAL",
        )

        membership = Membership.objects.create(
            user=user,
            organization=organization,
            username=derive_username(organization=organization, user=user, preferred=username),
            role=Membership.Role.OWNER,
            status=Membership.Status.ACTIVE,
            default_location=location,
        )

        from apps.expenses.models import ExpenseCategory

        # Un negocio nuevo debe poder registrar un gasto sin configurar nada
        # primero; son editables y desactivables como cualquier otra fila.
        ExpenseCategory.objects.bulk_create(
            [
                ExpenseCategory(organization=organization, name=name)
                for name in DEFAULT_EXPENSE_CATEGORIES
            ]
        )

        from apps.subscriptions.services import start_trial_subscription

        start_trial_subscription(organization=organization)

        record_audit(
            organization=organization,
            action="organization.created",
            actor=user,
            obj=organization,
            metadata={"name": name},
        )

    return membership
