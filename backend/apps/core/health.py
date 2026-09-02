"""Liveness and readiness.

Unauthenticated on purpose: a load balancer has no credentials. It reports
whether the process can reach its dependencies and nothing about the business,
so it leaks nothing worth having.
"""
from __future__ import annotations

from django.core.cache import cache
from django.db import connection
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []

    @extend_schema(responses={200: None, 503: None})
    def get(self, request):
        checks = {"database": self._check_database(), "cache": self._check_cache()}
        healthy = all(checks.values())
        return Response(
            {"status": "ok" if healthy else "degraded", "checks": checks},
            status=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    @staticmethod
    def _check_database() -> bool:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            return True
        except Exception:
            return False

    @staticmethod
    def _check_cache() -> bool:
        try:
            cache.set("health-check", "1", timeout=5)
            return cache.get("health-check") == "1"
        except Exception:
            return False
