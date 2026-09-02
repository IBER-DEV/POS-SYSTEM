"""Invitaciones: emisión del token, resolución y correo.

El token sigue el mismo patrón que el de una terminal registrada
(apps.synchronization.selectors): viaja como `<id>.<secreto>`, se guarda solo
el hash del secreto, y resolverlo es un lookup indexado por id más una
comparación de hash. Así el enlace se puede revocar, caduca, y una copia de la
base de datos no permite entrar a ningún negocio.
"""
from __future__ import annotations

import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone

from .models import Invitation


def issue_invitation_token(invitation: Invitation) -> str:
    """Emite el token, guarda su hash y devuelve el valor en claro una sola vez."""
    secret = secrets.token_urlsafe(32)
    invitation.token = make_password(secret)
    invitation.expires_at = timezone.now() + timedelta(days=settings.INVITATION_TTL_DAYS)
    invitation.status = Invitation.Status.PENDING
    invitation.save(update_fields=["token", "expires_at", "status", "updated_at"])
    return f"{invitation.pk.hex}.{secret}"


def resolve_invitation(raw_token: str | None) -> Invitation | None:
    """La invitación abierta que corresponde a un token, o None.

    Devuelve None también para las caducadas, revocadas y ya aceptadas: quien
    llama no tiene por qué distinguir entre ellas, y decírselo solo ayudaría a
    sondear qué enlaces existieron.
    """
    if not raw_token or "." not in raw_token:
        return None

    invitation_id, _, secret = raw_token.partition(".")
    invitation = (
        Invitation.objects.select_related("organization")
        .filter(pk=_as_uuid(invitation_id), status=Invitation.Status.PENDING)
        .first()
    )
    if invitation is None or invitation.is_expired:
        return None
    if not check_password(secret, invitation.token):
        return None
    return invitation


def send_invitation_email(invitation: Invitation, raw_token: str) -> None:
    """Envía el enlace. En desarrollo el backend de consola lo imprime."""
    link = f"{settings.FRONTEND_URL}/invitacion/{raw_token}"
    body = render_to_string(
        "accounts/invitation_email.txt",
        {
            "organization": invitation.organization.name,
            "role": invitation.get_role_display(),
            "link": link,
            "days": settings.INVITATION_TTL_DAYS,
        },
    )
    send_mail(
        subject=f"Te invitaron a {invitation.organization.name}",
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[invitation.email],
        # Una invitación no debe reventar el alta si el SMTP está caído: queda
        # creada y el dueño puede reenviarla.
        fail_silently=True,
    )


def _as_uuid(value: str):
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError):
        # Un id mal formado no debe lanzar: un token ilegible es simplemente inválido.
        return uuid.UUID(int=0)
