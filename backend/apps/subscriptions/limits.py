"""Plan limit enforcement.

Kept as a handful of explicit calls at the few places that create billable
resources. A generic quota framework would be more code than the product needs
today.
"""
from __future__ import annotations

from apps.core.exceptions import PlanLimitExceeded

from .models import Subscription

_RESOURCES = {
    "users": ("max_users", "users"),
    "locations": ("max_locations", "locations"),
    "products": ("max_products", "products"),
}


def enforce_limit(*, organization, resource: str, current_count: int) -> None:
    plan_field, label = _RESOURCES[resource]
    subscription = Subscription.objects.filter(organization=organization).select_related("plan").first()
    if subscription is None:
        return

    limit = getattr(subscription.plan, plan_field)
    if limit is not None and current_count >= limit:
        raise PlanLimitExceeded(
            f"Your {subscription.plan.name} plan allows at most {limit} {label}.",
            resource=resource,
            limit=limit,
            plan=subscription.plan.code,
        )
