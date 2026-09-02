"""Identidad global y membresías.

Una persona es una fila en `users` y su identidad global es el correo: con ella
entra una sola vez y elige después con cuál de sus negocios trabaja. Esa es la
única razón de ser de este modelo.

Pero un POS da de alta cajeros en el mostrador, sin correo, que entran con un
usuario y una contraseña. Por eso la identidad *local* vive en `Membership`:
ahí están `username`, `role`, `default_location` y los contadores de bloqueo.
Un cajero creado en el mostrador es un `User` sin correo, con una sola
membresía; el día que se le asigne un correo esa misma fila pasa a ser una
identidad global sin migrar nada.

`Membership` no es tenant-scoped a propósito: se lee antes de que exista
contexto de tenant (en el login) y de forma cruzada (los negocios de una
persona). El filtro por organización se escribe explícito en cada consulta.
"""
from __future__ import annotations

from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import BaseUserManager, PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

from apps.core.capabilities import capabilities_for_role
from apps.core.models import TimeStampedModel, UUIDModel

USERNAME_VALIDATOR = RegexValidator(
    r"^[a-z0-9][a-z0-9._-]{2,}$",
    "Use 3 or more lowercase letters, digits, dot, dash or underscore.",
)


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email=None, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        # `None`, no cadena vacía: en Postgres los NULL son distintos entre sí,
        # que es lo que permite tener muchos cajeros sin correo bajo una
        # restricción de unicidad global.
        user = self.model(email=self.normalize_email(email).lower() if email else None, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email=None, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if not email:
            raise ValueError("Superuser must have an email.")
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        # Los operadores de plataforma no son miembros de ningún negocio.
        return self.create_user(email, password, **extra_fields)


class User(UUIDModel, TimeStampedModel, AbstractBaseUser, PermissionsMixin):
    """La persona. Vive fuera de cualquier negocio."""

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        INACTIVE = "INACTIVE", "Inactive"

    email = models.EmailField(
        unique=True,
        null=True,
        blank=True,
        help_text="Identidad global. Null para personal creado en el mostrador.",
    )
    first_name = models.CharField(max_length=80, blank=True)
    last_name = models.CharField(max_length=80, blank=True)
    phone = models.CharField(max_length=30, blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)

    # Solo cuentan los fallos del login global por correo. El login local por
    # negocio tiene sus propios contadores en cada membresía.
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    is_staff = models.BooleanField(default=False, help_text="Platform operator, not a tenant role.")

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        db_table = "users"
        ordering = ["first_name", "email"]
        indexes = [models.Index(fields=["status"])]

    def __str__(self) -> str:
        return self.email or f"user:{self.pk}"

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip() or (self.email or "")

    @property
    def is_locked(self) -> bool:
        return self.locked_until is not None and self.locked_until > timezone.now()

    @property
    def is_active(self) -> bool:
        """Derivado, no almacenado: `status` es la única fuente de verdad."""
        return self.status == self.Status.ACTIVE and not self.is_locked


class Membership(UUIDModel, TimeStampedModel):
    """Lo que une a una persona con un negocio, y su identidad dentro de él.

    Nunca se borra: se pasa a SUSPENDED, porque el historial de ventas, cajas y
    auditoría apunta a ella y debe seguir siendo legible.
    """

    class Role(models.TextChoices):
        OWNER = "OWNER", "Owner"
        MANAGER = "MANAGER", "Manager"
        CASHIER = "CASHIER", "Cashier"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        INVITED = "INVITED", "Invited"
        SUSPENDED = "SUSPENDED", "Suspended"
        LOCKED = "LOCKED", "Locked"

    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="memberships"
    )
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="memberships"
    )

    username = models.CharField(max_length=40, validators=[USERNAME_VALIDATOR])

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CASHIER)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    default_location = models.ForeignKey(
        "organizations.Location",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="memberships",
    )

    failed_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "memberships"
        ordering = ["organization", "username"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "user"], name="uq_membership_org_user"),
            # El nombre de usuario es único dentro del negocio, no en la
            # plataforma: dos tiendas pueden tener cada una su propio `jperez`.
            models.UniqueConstraint(
                fields=["organization", "username"], name="uq_membership_org_username"
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "status"]),
            models.Index(fields=["user", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.username}@{self.organization_id}"

    @property
    def full_name(self) -> str:
        return self.user.full_name or self.username

    @property
    def is_locked(self) -> bool:
        if self.status == self.Status.LOCKED:
            return True
        return self.locked_until is not None and self.locked_until > timezone.now()

    @property
    def is_usable(self) -> bool:
        """Puede abrir sesión ahora mismo: activa, sin bloqueo y con la persona activa."""
        return self.status == self.Status.ACTIVE and not self.is_locked and self.user.is_active

    # -- Autorización ----------------------------------------------------
    @property
    def capabilities(self) -> frozenset[str]:
        return capabilities_for_role(self.role)

    def has_capability(self, capability: str) -> bool:
        return capability in self.capabilities


class Invitation(UUIDModel, TimeStampedModel):
    """Una invitación abierta a unirse a un negocio.

    El token se guarda hasheado y solo viaja en claro dentro del correo, igual
    que un token de terminal (ver apps.synchronization.selectors).
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        ACCEPTED = "ACCEPTED", "Accepted"
        REVOKED = "REVOKED", "Revoked"

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="invitations"
    )
    email = models.EmailField()
    role = models.CharField(
        max_length=20, choices=Membership.Role.choices, default=Membership.Role.CASHIER
    )
    default_location = models.ForeignKey(
        "organizations.Location",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invitations",
    )
    invited_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, related_name="sent_invitations"
    )

    token = models.CharField(max_length=128)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    membership = models.ForeignKey(
        "accounts.Membership", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        db_table = "invitations"
        ordering = ["-created_at"]
        constraints = [
            # Solo una invitación viva por correo y negocio; las aceptadas y
            # revocadas se conservan como historial.
            models.UniqueConstraint(
                fields=["organization", "email"],
                condition=models.Q(status="PENDING"),
                name="uq_invitation_pending_email",
            ),
        ]
        indexes = [models.Index(fields=["organization", "status"])]

    def __str__(self) -> str:
        return f"{self.email} -> {self.organization_id} ({self.status})"

    @property
    def is_expired(self) -> bool:
        return self.expires_at <= timezone.now()

    @property
    def is_open(self) -> bool:
        return self.status == self.Status.PENDING and not self.is_expired


# Alias a nivel de módulo para que drf-spectacular pueda nombrar estos enums en
# el esquema: su cargador de overrides no entra en clases anidadas.
USER_STATUS_CHOICES = User.Status.choices
MEMBERSHIP_ROLE_CHOICES = Membership.Role.choices
MEMBERSHIP_STATUS_CHOICES = Membership.Status.choices
INVITATION_STATUS_CHOICES = Invitation.Status.choices
