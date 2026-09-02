"""Autenticación JWT que además establece el contexto de tenant.

El token identifica a una persona; el claim `organization` dice con cuál de sus
negocios está trabajando. Ese claim no se cree por sí solo: en cada petición se
busca la membresía ACTIVA correspondiente, así que suspender a un empleado o
desactivar un negocio invalida las sesiones existentes de inmediato, sin
esperar a que el token expire.

Un token sin claim de organización (el de identidad, o el de un operador de
plataforma) no establece contexto y por tanto `HasOrganization` lo rechaza en
todo endpoint de negocio.
"""
from __future__ import annotations

from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken
from rest_framework_simplejwt.settings import api_settings

from .context import set_current_organization_id


class OrganizationJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        try:
            user_id = validated_token[api_settings.USER_ID_CLAIM]
        except KeyError:
            raise InvalidToken("Token contained no recognizable user identification") from None

        user = self.user_model.objects.filter(**{api_settings.USER_ID_FIELD: user_id}).first()
        if user is None:
            raise AuthenticationFailed("User not found", code="user_not_found")
        if not user.is_active:
            raise AuthenticationFailed("User is inactive", code="user_inactive")
        return user

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None

        user, token = result
        from apps.accounts.tokens import ORGANIZATION_CLAIM

        organization_id = token.get(ORGANIZATION_CLAIM)
        if organization_id is None:
            # Token de identidad, o operador de plataforma: sin contexto.
            return user, token

        from apps.accounts.models import Membership

        membership = (
            Membership.objects.select_related("organization", "default_location")
            .filter(
                user=user,
                organization_id=organization_id,
                status=Membership.Status.ACTIVE,
                organization__is_active=True,
            )
            .first()
        )
        # Un mismo mensaje para "el negocio no existe", "ya no trabajas ahí" y
        # "el negocio está desactivado": el token no debe servir para averiguar
        # cuál de las tres es.
        if membership is None or membership.is_locked:
            raise AuthenticationFailed("This session is no longer valid.")

        set_current_organization_id(membership.organization_id)
        request.organization = membership.organization
        request.membership = membership
        return user, token
