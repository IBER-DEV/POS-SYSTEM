"""Lookups that run before a tenant context exists."""
from __future__ import annotations

import secrets

from django.contrib.auth.hashers import check_password, make_password
from django.utils import timezone

from .models import Device

DEVICE_TOKEN_HEADER = "X-Device-Token"


def issue_device_token(device) -> str:
    """Mint a terminal token, store its hash, return the clear value once.

    The token carries the device id in front of the secret (`<uuid>.<secret>`)
    so a login can find the row with one indexed lookup instead of hashing its
    way through every terminal on the platform. Only the secret half is
    confidential, and only its hash is stored.
    """
    secret = secrets.token_urlsafe(32)
    device.token = make_password(secret)
    device.token_issued_at = timezone.now()
    device.save(update_fields=["token", "token_issued_at", "updated_at"])
    return f"{device.pk.hex}.{secret}"


def resolve_device(raw_token: str | None):
    """The registered terminal a login request comes from, or None.

    `all_objects` on purpose: this runs at login, before any tenant context
    exists - resolving the organization is precisely what it is for. The lookup
    is keyed by the token alone, so nothing here can be steered by the caller.
    """
    if not raw_token or "." not in raw_token:
        return None

    device_id, _, secret = raw_token.partition(".")
    device = (
        Device.all_objects.select_related("organization")
        .filter(pk=_as_uuid(device_id), is_active=True, organization__is_active=True)
        .exclude(token="")
        .first()
    )
    if device is None or not check_password(secret, device.token):
        return None
    return device


def _as_uuid(value: str):
    import uuid

    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError):
        # A malformed id must not raise: an unparseable token is simply invalid.
        return uuid.UUID(int=0)
