from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core import capabilities as caps
from apps.core.audit import record_audit
from apps.core.permissions import HasCapability, HasOrganization
from apps.core.views import TenantModelViewSet
from apps.subscriptions.limits import enforce_limit

from .models import Location
from .serializers import LocationSerializer, OrganizationSerializer


class CurrentOrganizationViewSet(viewsets.ViewSet):
    """The tenant is implicit in the token; there is no organization list endpoint.

    Exposing `/organizations/` as a collection would invite exactly the kind of
    id-guessing this architecture is built to prevent.
    """

    permission_classes = [HasOrganization, HasCapability]
    read_capability = caps.ORGANIZATION_READ
    write_capability = caps.ORGANIZATION_MANAGE
    serializer_class = OrganizationSerializer

    @extend_schema(responses={200: OrganizationSerializer})
    def list(self, request):
        return Response(OrganizationSerializer(request.organization).data)

    @extend_schema(request=OrganizationSerializer, responses={200: OrganizationSerializer})
    @action(detail=False, methods=["patch"], url_path="settings")
    def update_settings(self, request):
        serializer = OrganizationSerializer(request.organization, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        record_audit(
            organization=request.organization,
            action="organization.updated",
            actor=request.user,
            obj=request.organization,
            metadata={"fields": sorted(request.data.keys())},
        )
        return Response(serializer.data)


class LocationViewSet(TenantModelViewSet):
    serializer_class = LocationSerializer
    model = Location
    read_capability = caps.ORGANIZATION_READ
    write_capability = caps.ORGANIZATION_MANAGE
    filterset_fields = ["is_active", "is_default"]
    search_fields = ["name", "code"]

    def perform_create(self, serializer):
        enforce_limit(
            organization=self.request.organization,
            resource="locations",
            current_count=Location.objects.count(),
        )
        super().perform_create(serializer)
        record_audit(
            organization=self.request.organization,
            action="location.created",
            actor=self.request.user,
            obj=serializer.instance,
        )

    def perform_destroy(self, instance):
        # Locations are referenced by the inventory ledger; deactivate instead
        # of deleting so history stays readable.
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])
