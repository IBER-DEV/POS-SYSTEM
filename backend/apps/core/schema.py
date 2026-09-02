"""OpenAPI glue for drf-spectacular."""
from drf_spectacular.extensions import OpenApiAuthenticationExtension


class OrganizationJWTScheme(OpenApiAuthenticationExtension):
    """Documents the bearer token. The tenant comes from the account, not a claim."""

    target_class = "apps.core.authentication.OrganizationJWTAuthentication"
    name = "organizationJWT"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": (
                "Access token from /api/v1/auth/login/. An account belongs to "
                "exactly one business, so the tenant is derived from the account "
                "on every request - there is nothing to select and nothing to switch."
            ),
        }
