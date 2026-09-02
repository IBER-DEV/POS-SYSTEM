"""Credenciales: verificación y bloqueo.

Hay dos caminos y cada uno tiene sus propios contadores:

- El *global*, correo + contraseña, contra `User`. Es el que habilita SSO.
- El *local*, usuario + contraseña dentro de un negocio, contra `Membership`.
  El bloqueo debe contarse por negocio: los intentos fallidos en una tienda no
  deben cerrar la caja de otra.

Ninguna búsqueda de aquí pasa por `django.contrib.auth.authenticate`: ese
camino resuelve una cuenta por un nombre de usuario único global, que aquí no
existe.
"""
from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import F
from django.utils import timezone

from .models import Membership

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15

User = get_user_model()


# -- Búsquedas -----------------------------------------------------------


def find_membership(*, organization, username: str):
    """La membresía de un nombre de usuario dentro de un negocio, o None.

    `Membership` no es tenant-scoped (se lee antes de que exista contexto), así
    que la organización se pasa explícita aquí y en cualquier otra búsqueda.
    """
    if not organization or not username:
        return None
    return (
        Membership.objects.select_related("user", "organization", "default_location")
        .filter(organization=organization, username=username.strip().lower())
        .first()
    )


def find_identity(*, email: str):
    """La persona detrás de un correo, o None."""
    if not email:
        return None
    return User.objects.filter(email=email.strip().lower()).first()


def active_memberships(user):
    """Los negocios en los que la persona puede trabajar ahora, el más reciente primero."""
    return (
        Membership.objects.select_related("organization", "default_location")
        .filter(user=user, status=Membership.Status.ACTIVE, organization__is_active=True)
        .order_by(F("last_used_at").desc(nulls_last=True), "organization__name")
    )


# -- Verificación --------------------------------------------------------


def verify_identity(user, password: str | None) -> bool:
    """Comprueba la contraseña global y mantiene el bloqueo de la cuenta.

    Devuelve False para una cuenta inactiva o bloqueada sin llegar a probar el
    secreto, de modo que un bloqueo no se pueda atravesar a fuerza de intentos.
    """
    if user is None or not password:
        return False
    if user.status != User.Status.ACTIVE or user.is_locked:
        return False

    ok = user.has_usable_password() and user.check_password(password)
    if ok:
        _clear(user)
    else:
        _register_failure(user, lock_status=None)
    return ok


def verify_credentials(membership, *, password: str | None = None) -> bool:
    """Comprueba la contraseña dentro de un negocio y actualiza sus contadores.

    La contraseña es la global de la persona, porque es la misma en todos sus
    negocios. El bloqueo, en cambio, es siempre local.
    """
    if membership is None:
        return False
    if membership.status != Membership.Status.ACTIVE or membership.is_locked:
        return False
    if not membership.user.is_active:
        return False

    if password is not None:
        user = membership.user
        ok = user.has_usable_password() and user.check_password(password)
    else:
        ok = False

    if ok:
        _clear(membership)
    else:
        _register_failure(membership, lock_status=Membership.Status.LOCKED)
    return ok


# -- Bloqueo -------------------------------------------------------------


def _register_failure(target, *, lock_status) -> None:
    """Cuenta un intento fallido y bloquea cuando se agota el presupuesto.

    El incremento va por UPDATE en la base de datos, no leyendo y escribiendo,
    para que varios intentos simultáneos no se pisen el contador.
    """
    type(target).objects.filter(pk=target.pk).update(failed_attempts=F("failed_attempts") + 1)
    target.refresh_from_db(fields=["failed_attempts"])
    if target.failed_attempts >= MAX_FAILED_ATTEMPTS:
        target.locked_until = timezone.now() + timedelta(minutes=LOCKOUT_MINUTES)
        fields = ["locked_until", "updated_at"]
        if lock_status is not None:
            target.status = lock_status
            fields.append("status")
        target.save(update_fields=fields)


def _clear(target) -> None:
    if target.failed_attempts or target.locked_until:
        target.failed_attempts = 0
        target.locked_until = None
        target.save(update_fields=["failed_attempts", "locked_until", "updated_at"])


def unlock(membership) -> None:
    """Desbloqueo por el dueño: limpia los contadores y reactiva la membresía."""
    membership.failed_attempts = 0
    membership.locked_until = None
    if membership.status == Membership.Status.LOCKED:
        membership.status = Membership.Status.ACTIVE
    membership.save(
        update_fields=["failed_attempts", "locked_until", "status", "updated_at"]
    )


def touch(membership) -> None:
    """Marca el negocio como el usado más recientemente, para ordenar el selector."""
    membership.last_used_at = timezone.now()
    membership.save(update_fields=["last_used_at", "updated_at"])
