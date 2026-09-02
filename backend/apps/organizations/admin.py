from django.contrib import admin

from .models import Location, Organization


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "tax_id", "currency", "is_active", "created_at")
    search_fields = ("name", "slug", "tax_id")
    list_filter = ("is_active", "country")


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "organization", "is_default", "is_active")
    list_filter = ("is_active", "is_default")
    search_fields = ("name", "code", "organization__name")

    def get_queryset(self, request):
        return Location.all_objects.select_related("organization")
