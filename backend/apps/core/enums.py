"""Enumerations shared across domains.

PaymentMethod lives here because sales record it and cash reconciles it; a
shared vocabulary avoids one app importing the other just for a constant.
"""
from django.db import models


class PaymentMethod(models.TextChoices):
    CASH = "CASH", "Efectivo"
    CARD = "CARD", "Tarjeta"
    TRANSFER = "TRANSFER", "Transferencia"
    OTHER = "OTHER", "Otro"

    @classmethod
    def affects_drawer(cls, method: str) -> bool:
        """Only cash physically enters or leaves the drawer.

        Card and transfer payments are recorded on the sale and reported per
        method at closing time, but they must not move the counted balance -
        otherwise every arqueo would show a false difference.
        """
        return method == cls.CASH

# Module-level alias so drf-spectacular can name this enum in the OpenAPI
# schema; its override loader cannot traverse into a nested class.
PAYMENT_METHOD_CHOICES = PaymentMethod.choices
