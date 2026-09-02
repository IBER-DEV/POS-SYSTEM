from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from apps.organizations.serializers import OrganizationSerializer

from .models import USERNAME_VALIDATOR, Invitation, Membership

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """La persona, tal como se la muestra a sí misma. Sin nada de un negocio."""

    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "full_name", "phone", "created_at"]
        read_only_fields = fields


class ProfileUpdateSerializer(serializers.ModelSerializer):
    """Lo que cada quien puede cambiar de su propia cuenta global."""

    class Meta:
        model = User
        fields = ["first_name", "last_name", "phone", "email"]

    def validate_email(self, value):
        value = (value or "").strip().lower() or None
        if value and User.objects.filter(email=value).exclude(pk=self.instance.pk).exists():
            raise serializers.ValidationError("Ese correo ya pertenece a otra cuenta.")
        return value


class MembershipBriefSerializer(serializers.ModelSerializer):
    """Una fila del selector de negocios.

    La membresía se llama `membership` y no `id` para que una fila del selector
    y un payload de sesión nombren la misma cosa igual: el cliente pasa de una
    a la otra sin traducir nada.
    """

    membership = serializers.UUIDField(source="id", read_only=True)
    organization = OrganizationSerializer(read_only=True)

    class Meta:
        model = Membership
        fields = ["membership", "organization", "username", "role", "default_location", "last_used_at"]
        read_only_fields = fields


# -- Autenticación -------------------------------------------------------


class LoginSerializer(serializers.Serializer):
    """Dos formas de entrar, una sola forma de pedirlo.

    - Identidad global: `email` + `password`. Devuelve la lista de negocios.
    - Negocio explícito: `organization` (slug, o resuelto por una terminal
      registrada vía X-Device-Token) + `username` + `password`.
    """

    email = serializers.EmailField(required=False, allow_blank=True)
    organization = serializers.SlugField(required=False, allow_blank=True)
    username = serializers.CharField(max_length=40, required=False, allow_blank=True)
    password = serializers.CharField(
        write_only=True, required=False, allow_blank=True, style={"input_type": "password"}
    )

    def validate(self, attrs):
        if not attrs.get("password"):
            raise serializers.ValidationError({"detail": "Se requiere una contraseña."})
        if not attrs.get("email") and not attrs.get("username"):
            raise serializers.ValidationError(
                {"detail": "Indica un correo, o un usuario junto con el negocio."}
            )
        return attrs


class SelectOrganizationSerializer(serializers.Serializer):
    """Con qué negocio se va a trabajar. Acepta el id o el slug, lo que tenga el cliente."""

    organization = serializers.CharField()


class RegistrationSerializer(serializers.Serializer):
    """Alta por cuenta propia: crea la persona y su primer negocio."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, validators=[validate_password])
    first_name = serializers.CharField(max_length=80, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=80, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True)
    username = serializers.CharField(
        max_length=40,
        required=False,
        allow_blank=True,
        validators=[USERNAME_VALIDATOR],
        help_text="Opcional. El usuario con el que entrarás desde una caja; se deriva del correo.",
    )
    organization_name = serializers.CharField(max_length=140)
    legal_name = serializers.CharField(max_length=180, required=False, allow_blank=True)
    tax_id = serializers.CharField(max_length=40, required=False, allow_blank=True)

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError(
                "Ya existe una cuenta con ese correo. Inicia sesión y crea el negocio desde ahí."
            )
        return value


class OrganizationCreateSerializer(serializers.Serializer):
    """Un negocio más para alguien que ya tiene cuenta."""

    name = serializers.CharField(max_length=140)
    legal_name = serializers.CharField(max_length=180, required=False, allow_blank=True)
    tax_id = serializers.CharField(max_length=40, required=False, allow_blank=True)


# -- Empleados -----------------------------------------------------------


class EmployeeSerializer(serializers.ModelSerializer):
    """Cómo ve el dueño a alguien de su equipo: la membresía, con su persona al lado."""

    full_name = serializers.CharField(read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)
    phone = serializers.CharField(source="user.phone", read_only=True)
    user_id = serializers.UUIDField(source="user.id", read_only=True)
    capabilities = serializers.SerializerMethodField()
    is_locked = serializers.BooleanField(read_only=True)

    class Meta:
        model = Membership
        fields = [
            "id",
            "user_id",
            "username",
            "first_name",
            "last_name",
            "full_name",
            "email",
            "phone",
            "role",
            "status",
            "default_location",
            "capabilities",
            "is_locked",
            "created_at",
        ]
        read_only_fields = fields

    def get_capabilities(self, obj) -> list[str]:
        return sorted(obj.capabilities)


class EmployeeCreateSerializer(serializers.Serializer):
    """Alta directa, en el mostrador.

    Sin invitación y sin aceptación: la cuenta existe y funciona en cuanto esto
    responde, con el usuario y la contraseña que el dueño le asigna aquí mismo.
    El correo es obligatorio porque es con lo que esta persona inicia sesión;
    si ya tiene cuenta con ese correo, se vincula esa persona en vez de crear
    otra.
    """

    username = serializers.CharField(max_length=40, validators=[USERNAME_VALIDATOR])
    first_name = serializers.CharField(max_length=80)
    last_name = serializers.CharField(max_length=80, required=False, allow_blank=True)
    role = serializers.ChoiceField(choices=Membership.Role.choices)
    password = serializers.CharField(
        write_only=True,
        validators=[validate_password],
        help_text="Contraseña con la que este empleado inicia sesión.",
    )
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True)
    default_location = serializers.UUIDField(required=False, allow_null=True)

    def validate_username(self, value):
        return value.strip().lower()

    def validate_email(self, value):
        return value.strip().lower()


class EmployeeUpdateSerializer(serializers.ModelSerializer):
    """Lo que un negocio puede cambiar de alguien de su equipo.

    Solo campos de la membresía. El nombre, el correo y el teléfono son de la
    persona y pueden estar compartidos con otro negocio, así que se editan
    aparte y con condiciones (ver EmployeeViewSet.perform_update).
    """

    class Meta:
        model = Membership
        fields = ["username", "role", "status", "default_location"]

    def validate_username(self, value):
        value = value.strip().lower()
        USERNAME_VALIDATOR(value)
        taken = (
            Membership.objects.filter(
                organization=self.instance.organization_id, username=value
            )
            .exclude(pk=self.instance.pk)
            .exists()
        )
        if taken:
            raise serializers.ValidationError("Alguien en este negocio ya usa ese usuario.")
        return value

    def validate_status(self, value):
        if value == Membership.Status.LOCKED:
            raise serializers.ValidationError(
                "Una cuenta se bloquea por intentos fallidos, no a mano. Usa unlock para desbloquearla."
            )
        if value == Membership.Status.INVITED:
            raise serializers.ValidationError("No se puede devolver a alguien al estado de invitado.")
        return value


class EmployeeProfileUpdateSerializer(serializers.ModelSerializer):
    """Datos personales de alguien del equipo, editables solo si no los comparte."""

    class Meta:
        model = User
        fields = ["first_name", "last_name", "phone", "email"]

    def validate_email(self, value):
        value = (value or "").strip().lower() or None
        if value and User.objects.filter(email=value).exclude(pk=self.instance.pk).exists():
            raise serializers.ValidationError("Ese correo ya pertenece a otra cuenta.")
        return value


# -- Invitaciones --------------------------------------------------------


class InvitationSerializer(serializers.ModelSerializer):
    invited_by_email = serializers.EmailField(source="invited_by.email", read_only=True, default=None)

    class Meta:
        model = Invitation
        fields = [
            "id",
            "email",
            "role",
            "default_location",
            "status",
            "expires_at",
            "accepted_at",
            "invited_by_email",
            "created_at",
        ]
        read_only_fields = fields


class InvitationCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=Membership.Role.choices)
    default_location = serializers.UUIDField(required=False, allow_null=True)

    def validate_email(self, value):
        return value.strip().lower()


class InvitationPreviewSerializer(serializers.Serializer):
    """Lo que ve quien abre el enlace, antes de decidir si acepta."""

    organization = serializers.CharField()
    email = serializers.EmailField()
    role = serializers.CharField()
    expires_at = serializers.DateTimeField()
    # Le dice al frontend si pedir una contraseña nueva o solo confirmar.
    account_exists = serializers.BooleanField()


class InvitationAcceptSerializer(serializers.Serializer):
    token = serializers.CharField()
    username = serializers.CharField(max_length=40, validators=[USERNAME_VALIDATOR])
    password = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        validators=[validate_password],
        help_text="Obligatoria si aún no tienes cuenta; se ignora si ya tienes una.",
    )
    first_name = serializers.CharField(max_length=80, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=80, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True)

    def validate_username(self, value):
        return value.strip().lower()
