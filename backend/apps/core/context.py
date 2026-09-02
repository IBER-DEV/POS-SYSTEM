"""Tenant context.

The active organization is derived from the authenticated token and stored in a
contextvar for the duration of the request. It is never read from a query
parameter, header or request body: a client must not be able to choose its own
tenant. See ARCHITECTURE.md ("Tenancy").
"""
from __future__ import annotations

import contextvars
from contextlib import contextmanager
from typing import Any

_current_organization_id: contextvars.ContextVar[Any] = contextvars.ContextVar(
    "current_organization_id", default=None
)
_unscoped: contextvars.ContextVar[bool] = contextvars.ContextVar("tenant_unscoped", default=False)


def get_current_organization_id():
    """Return the organization id bound to the current execution context, if any."""
    return _current_organization_id.get()


def set_current_organization_id(organization_id):
    """Bind an organization to the current context. Returns the token to reset it."""
    return _current_organization_id.set(organization_id)


def reset_organization(token) -> None:
    _current_organization_id.reset(token)


def clear_current_organization() -> None:
    _current_organization_id.set(None)


def is_unscoped() -> bool:
    return _unscoped.get()


@contextmanager
def tenant_context(organization_id):
    """Run a block bound to a specific organization (background jobs, tests, shell)."""
    token = _current_organization_id.set(getattr(organization_id, "pk", organization_id))
    try:
        yield
    finally:
        _current_organization_id.reset(token)


@contextmanager
def unscoped():
    """Escape hatch: disable tenant filtering.

    Only for cross-tenant maintenance (platform admin, reconciliation commands).
    Never call this from a request-handling code path.
    """
    token = _unscoped.set(True)
    try:
        yield
    finally:
        _unscoped.reset(token)
