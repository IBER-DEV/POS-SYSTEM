from __future__ import annotations

from .context import clear_current_organization


class TenantContextMiddleware:
    """Clears the tenant contextvar around every request.

    Workers are reused across requests; without this a leftover organization
    from a previous request could scope the next one. Cheap insurance against
    the worst possible bug in a multi-tenant system.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        clear_current_organization()
        try:
            return self.get_response(request)
        finally:
            clear_current_organization()
