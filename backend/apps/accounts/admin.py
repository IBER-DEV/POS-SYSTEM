from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Invitation, Membership, User


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0
    fields = ("organization", "username", "role", "status", "default_location", "last_used_at")
    readonly_fields = ("last_used_at",)
    autocomplete_fields = ("organization", "default_location")


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("email",)
    list_display = ("email", "full_name", "status", "is_staff")
    # `is_active` es una propiedad derivada de `status`, así que no se puede
    # filtrar por ella; `status` es la columna real y dice más de todos modos.
    list_filter = ("status", "is_staff", "is_superuser")
    search_fields = ("email", "first_name", "last_name", "phone")
    readonly_fields = ("last_login", "created_at", "updated_at")
    inlines = [MembershipInline]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal", {"fields": ("first_name", "last_name", "phone")}),
        ("Estado", {"fields": ("status", "failed_attempts", "locked_until")}),
        ("Plataforma", {"fields": ("is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Fechas", {"fields": ("last_login", "created_at", "updated_at")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "password1", "password2")}),
    )


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("username", "organization", "user", "role", "status", "last_used_at")
    list_filter = ("role", "status")
    search_fields = ("username", "user__email", "user__first_name", "user__last_name")
    readonly_fields = ("created_at", "updated_at", "last_used_at")
    autocomplete_fields = ("user", "organization", "default_location")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user", "organization")


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = ("email", "organization", "role", "status", "expires_at", "accepted_at")
    list_filter = ("status", "role")
    search_fields = ("email",)
    # El token está hasheado y no se puede leer: mostrarlo solo confundiría.
    exclude = ("token",)
    readonly_fields = ("created_at", "updated_at", "accepted_at", "membership")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("organization")
