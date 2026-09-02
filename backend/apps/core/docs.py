"""Self-hosted API reference.

drf-spectacular already ships a Swagger UI at /api/v1/docs/, loaded from its
own vendored static assets. This view is an alternative renderer (Scalar)
that reads the same schema.

Deliberately NOT the CDN-script version Scalar's own docs recommend
(`<script src="https://cdn.jsdelivr.net/npm/@scalar/api-reference">`): a CDN
outage would take the API docs down with it for no reason, since the whole
point of a reference page is that it works when everything else is on fire.
The bundle is vendored at apps/core/static/core/vendor/ and served by
whitenoise/staticfiles like any other static file - no network dependency
beyond this server.
"""
from __future__ import annotations

from django.views.generic import TemplateView


class ApiReferenceView(TemplateView):
    template_name = "core/api_reference.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Retail POS SaaS"
        context["schema_url"] = "/api/v1/schema/"
        return context
