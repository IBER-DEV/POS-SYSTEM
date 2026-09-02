"""Server-side authorization. The frontend hiding a button is never the control."""
from __future__ import annotations

from rest_framework.permissions import SAFE_METHODS, BasePermission

from .exceptions import SubscriptionInactive


class HasOrganization(BasePermission):
    """Requires a token belonging to an active account inside a business."""

    message = "No active organization in this session."

    def has_permission(self, request, view):
        return getattr(request, "organization", None) is not None


class HasCapability(BasePermission):
    """Checks the capability the view declares for the current action.

    Views declare `read_capability` / `write_capability`, optionally overridden
    per action via `capability_overrides = {"destroy": "products.write"}`.
    """

    message = "Your role does not allow this action."

    def has_permission(self, request, view):
        # Las capacidades salen del rol dentro de este negocio, no de la
        # persona: la misma cuenta puede ser dueña aquí y cajera al lado.
        membership = getattr(request, "membership", None)
        if membership is None:
            return False

        required = self._required_capability(request, view)
        if required is None:
            return True
        return membership.has_capability(required)

    @staticmethod
    def _required_capability(request, view) -> str | None:
        overrides = getattr(view, "capability_overrides", {}) or {}
        action = getattr(view, "action", None)
        if action and action in overrides:
            return overrides[action]
        if request.method in SAFE_METHODS:
            return getattr(view, "read_capability", None)
        return getattr(view, "write_capability", None)


class SubscriptionAllowsWrites(BasePermission):
    """Blocks writes once a subscription is cancelled or expired.

    Reads stay open on purpose: a store that stops paying must still be able to
    get its own data out. PAST_DUE also keeps writing - cutting a shop off
    mid-sale over billing is a product decision nobody has made (see
    Subscription.is_usable).
    """

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True

        organization = getattr(request, "organization", None)
        if organization is None:
            return True  # HasOrganization already rejected this request.

        subscription = getattr(request, "_subscription", None)
        if subscription is None:
            from apps.subscriptions.models import Subscription

            subscription = Subscription.objects.filter(organization=organization).first()
            request._subscription = subscription

        if subscription is not None and not subscription.is_usable:
            raise SubscriptionInactive(
                f"The subscription for {organization.name} is {subscription.status.lower()}.",
                status=subscription.status,
            )
        return True
