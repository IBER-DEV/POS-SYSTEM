"""Minimal admin.

The Django admin is a platform-operator tool, not a tenant-facing surface, so
only models that are meaningful across tenants are registered here. Tenant data
is reached through the API, where isolation is enforced.
"""
from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "organization", "action", "actor_label", "object_type", "object_id")
    list_filter = ("action",)
    search_fields = ("actor_label", "object_id")
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def get_queryset(self, request):
        return AuditLog.all_objects.select_related("organization")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
