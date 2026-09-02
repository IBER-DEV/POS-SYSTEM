"""Invitar por correo a alguien que quizá ya tenga cuenta en otro negocio."""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone

from apps.accounts.invitations import issue_invitation_token
from apps.accounts.models import Invitation, Membership

pytestmark = pytest.mark.django_db

INVITATIONS = "/api/v1/invitations/"
ACCEPT = "/api/v1/auth/invitations/accept/"


def invite(client, email="nuevo@example.com", role="CASHIER"):
    return client.post(INVITATIONS, {"email": email, "role": role}, format="json")


def token_for(invitation):
    """El token en claro solo existe en el correo, así que aquí se emite otro."""
    return issue_invitation_token(invitation)


# -- Enviar --------------------------------------------------------------


def test_inviting_sends_a_link_and_leaves_the_invitation_pending(tenant_a, client_for):
    mail.outbox.clear()

    response = invite(client_for(tenant_a.owner, tenant_a.org))

    assert response.status_code == 201
    assert response.json()["status"] == "PENDING"
    assert len(mail.outbox) == 1
    assert "nuevo@example.com" in mail.outbox[0].to
    # El token viaja en el correo y solo ahí: en la base de datos está hasheado.
    invitation = Invitation.objects.get()
    assert invitation.token not in mail.outbox[0].body


def test_a_cashier_cannot_invite_anyone(tenant_a, make_employee, client_for):
    cashier = make_employee(tenant_a, role=Membership.Role.CASHIER)

    assert invite(client_for(cashier)).status_code == 403


def test_inviting_someone_who_already_works_here_is_refused(tenant_a, make_identity, join, client_for):
    person = make_identity(email="ya@example.com")
    join(tenant_a, person)

    response = invite(client_for(tenant_a.owner, tenant_a.org), email="ya@example.com")

    assert response.status_code == 409
    assert response.json()["code"] == "already_member"


def test_inviting_the_same_email_twice_replaces_the_first_link(tenant_a, client_for):
    client = client_for(tenant_a.owner, tenant_a.org)
    invite(client)
    first = Invitation.objects.get()

    invite(client)

    first.refresh_from_db()
    assert first.status == Invitation.Status.REVOKED
    assert Invitation.objects.filter(status=Invitation.Status.PENDING).count() == 1


# -- Aceptar -------------------------------------------------------------


def test_accepting_creates_the_person_and_the_membership(tenant_a, client_for, client):
    invite(client_for(tenant_a.owner, tenant_a.org))
    raw = token_for(Invitation.objects.get())

    response = client.post(
        ACCEPT,
        {"token": raw, "username": "jperez", "password": "ClaveDePrueba123", "first_name": "Juan"},
        content_type="application/json",
    )

    assert response.status_code == 201
    body = response.json()
    # Entra ya trabajando: aceptar es también iniciar sesión.
    assert body["scope"] == "session"
    assert body["organization"]["slug"] == tenant_a.org.slug
    assert body["role"] == "CASHIER"
    assert Membership.objects.filter(organization=tenant_a.org, username="jperez").exists()


def test_accepting_with_an_existing_account_only_adds_the_membership(
    tenant_a, tenant_b, make_identity, join, client_for, client
):
    """Lo que hace útil el SSO: una persona, dos negocios, una contraseña."""
    person = make_identity(email="doble@example.com", password="ClaveDePrueba123")
    join(tenant_b, person)

    invite(client_for(tenant_a.owner, tenant_a.org), email="doble@example.com")
    raw = token_for(Invitation.objects.get())

    response = client.post(
        ACCEPT, {"token": raw, "username": "doble"}, content_type="application/json"
    )

    assert response.status_code == 201
    assert Membership.objects.filter(user=person).count() == 2
    # No se le tocó la contraseña: aceptar no puede ser una forma de cambiarla.
    person.refresh_from_db()
    assert person.check_password("ClaveDePrueba123")


def test_a_new_person_must_choose_a_password(tenant_a, client_for, client):
    invite(client_for(tenant_a.owner, tenant_a.org))
    raw = token_for(Invitation.objects.get())

    response = client.post(
        ACCEPT, {"token": raw, "username": "jperez"}, content_type="application/json"
    )

    assert response.status_code == 400
    assert response.json()["code"] == "password_required"


def test_a_token_cannot_be_used_twice(tenant_a, client_for, client):
    invite(client_for(tenant_a.owner, tenant_a.org))
    raw = token_for(Invitation.objects.get())
    body = {"token": raw, "username": "jperez", "password": "ClaveDePrueba123"}

    assert client.post(ACCEPT, body, content_type="application/json").status_code == 201
    again = client.post(
        ACCEPT, {**body, "username": "otro"}, content_type="application/json"
    )

    assert again.status_code == 400
    assert again.json()["code"] == "invalid_invitation"


def test_an_expired_token_is_refused(tenant_a, client_for, client):
    invite(client_for(tenant_a.owner, tenant_a.org))
    invitation = Invitation.objects.get()
    raw = token_for(invitation)
    invitation.expires_at = timezone.now() - timedelta(seconds=1)
    invitation.save(update_fields=["expires_at"])

    response = client.post(
        ACCEPT,
        {"token": raw, "username": "jperez", "password": "ClaveDePrueba123"},
        content_type="application/json",
    )

    assert response.status_code == 400


def test_a_revoked_token_is_refused(tenant_a, client_for, client):
    owner = client_for(tenant_a.owner, tenant_a.org)
    invite(owner)
    invitation = Invitation.objects.get()
    raw = token_for(invitation)

    assert owner.delete(f"{INVITATIONS}{invitation.pk}/").status_code == 204

    response = client.post(
        ACCEPT,
        {"token": raw, "username": "jperez", "password": "ClaveDePrueba123"},
        content_type="application/json",
    )
    assert response.status_code == 400


def test_a_tampered_token_resolves_nothing(tenant_a, client_for, client):
    invite(client_for(tenant_a.owner, tenant_a.org))
    raw = token_for(Invitation.objects.get())

    response = client.post(
        ACCEPT,
        {"token": f"{raw}tampered", "username": "jperez", "password": "ClaveDePrueba123"},
        content_type="application/json",
    )

    assert response.status_code == 400


def test_an_invitation_only_opens_the_business_that_sent_it(
    tenant_a, tenant_b, client_for, client
):
    invite(client_for(tenant_a.owner, tenant_a.org))
    raw = token_for(Invitation.objects.get())

    body = client.post(
        ACCEPT,
        {"token": raw, "username": "jperez", "password": "ClaveDePrueba123"},
        content_type="application/json",
    ).json()

    assert body["organization"]["slug"] == tenant_a.org.slug
    assert not Membership.objects.filter(organization=tenant_b.org, username="jperez").exists()


# -- Ver el enlace antes de aceptar --------------------------------------


def test_the_preview_says_whether_an_account_already_exists(
    tenant_a, make_identity, client_for, client
):
    make_identity(email="conocido@example.com")
    invite(client_for(tenant_a.owner, tenant_a.org), email="conocido@example.com")
    raw = token_for(Invitation.objects.get())

    data = client.get(f"/api/v1/auth/invitations/{raw}/").json()

    assert data["organization"] == tenant_a.org.name
    assert data["account_exists"] is True


def test_the_preview_of_an_unknown_token_is_a_404(client, db):
    assert client.get("/api/v1/auth/invitations/nada.nada/").status_code == 404


# -- Límites del plan ----------------------------------------------------


def test_a_pending_invitation_takes_up_a_seat(tenant_a, client_for):
    """Si no contara, invitar a diez personas saltaría el límite del plan."""
    from apps.core.context import tenant_context
    from apps.subscriptions.models import Subscription

    with tenant_context(tenant_a.org.pk):
        subscription = Subscription.objects.get(organization=tenant_a.org)
        subscription.plan.max_users = 2
        subscription.plan.save(update_fields=["max_users"])

    client = client_for(tenant_a.owner, tenant_a.org)
    assert invite(client, email="uno@example.com").status_code == 201  # dueño + 1 = 2
    blocked = invite(client, email="dos@example.com")

    assert blocked.status_code == 402
    assert blocked.json()["code"] == "plan_limit_exceeded"
