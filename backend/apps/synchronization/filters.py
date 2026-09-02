from __future__ import annotations

import django_filters as filters

from .models import Device, SyncOperation


class DeviceFilter(filters.FilterSet):
    location = filters.UUIDFilter(field_name="location_id")

    class Meta:
        model = Device
        fields = ["is_active"]


class SyncOperationFilter(filters.FilterSet):
    device = filters.UUIDFilter(field_name="device_id")
    received_after = filters.IsoDateTimeFilter(field_name="received_at", lookup_expr="gte")
    received_before = filters.IsoDateTimeFilter(field_name="received_at", lookup_expr="lte")

    class Meta:
        model = SyncOperation
        fields = ["status", "operation_type"]
