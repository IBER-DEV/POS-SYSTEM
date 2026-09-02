"""Audit helper used by every service that performs a critical operation."""
from __future__ import annotations

from .json import to_jsonable
from .models import AuditLog


def record_audit(
    *,
    organization,
    action: str,
    actor=None,
    obj=None,
    object_type: str = "",
    object_id: str = "",
    metadata: dict | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    if obj is not None:
        object_type = object_type or obj.__class__.__name__
        object_id = object_id or str(obj.pk)

    return AuditLog.objects.create(
        organization=organization,
        action=action,
        actor=actor,
        actor_label=getattr(actor, "email", "") or "",
        object_type=object_type,
        object_id=str(object_id),
        metadata=to_jsonable(metadata) or {},
        ip_address=ip_address,
    )
