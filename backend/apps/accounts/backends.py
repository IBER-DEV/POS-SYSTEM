"""El único backend de autenticación de Django, y sirve solo al admin.

Las credenciales de tienda (usuario + contraseña dentro de un negocio) nunca pasan por
`django.contrib.auth.authenticate`: ese nombre de usuario es único por
organización, así que resolverlo a secas sería ambiguo. Van por
apps.accounts.services, que siempre parte de una organización.

Subclasear `ModelBackend` en vez de `BaseBackend` mantiene `has_perm`,
`get_all_permissions` y compañía funcionando para el admin; solo cambia la
búsqueda de la cuenta.
"""
from __future__ import annotations

from django.contrib.auth.backends import ModelBackend

from .models import User


class PlatformStaffBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        email = username or kwargs.get(User.USERNAME_FIELD)
        if not email or not password:
            return None

        user = User.objects.filter(
            email=email.strip().lower(), is_staff=True, memberships__isnull=True
        ).first()
        if user is None:
            # Misma forma en tiempo constante que ModelBackend: se hashea de
            # todos modos para que una cuenta inexistente no se distinga.
            User().set_password(password)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
