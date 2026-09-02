from __future__ import annotations

from .models import Location


def default_location(organization=None):
    """The location an operation uses when the client does not send one.

    Single-store tenants never have to think about locations; multi-store ones
    always send it explicitly.
    """
    queryset = Location.objects.filter(is_active=True)
    return queryset.filter(is_default=True).first() or queryset.order_by("created_at").first()
