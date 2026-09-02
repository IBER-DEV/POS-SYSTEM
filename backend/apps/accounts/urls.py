from django.urls import path

from .views import (
    CreateOrganizationView,
    InvitationAcceptView,
    InvitationPreviewView,
    LoginView,
    MeView,
    OrganizationChoicesView,
    RefreshView,
    RegisterView,
    SelectOrganizationView,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("refresh/", RefreshView.as_view(), name="token-refresh"),
    path("me/", MeView.as_view(), name="me"),
    # Elegir negocio y cambiar de negocio son la misma operación.
    path("organizations/", OrganizationChoicesView.as_view(), name="organization-choices"),
    path(
        "select-organization/", SelectOrganizationView.as_view(), name="select-organization"
    ),
    # Abrir un negocio más sin crear otra cuenta: el sentido del SSO.
    path("organizations/new/", CreateOrganizationView.as_view(), name="organization-create"),
    # Públicos: quien acepta una invitación todavía no tiene sesión.
    path(
        "invitations/accept/", InvitationAcceptView.as_view(), name="invitation-accept"
    ),
    path(
        "invitations/<str:token>/", InvitationPreviewView.as_view(), name="invitation-preview"
    ),
]
