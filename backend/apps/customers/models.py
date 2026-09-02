"""Customers.

Deliberately small. A clothing store needs to know who bought what and how to
reach them; it does not need a CRM. Purchase history is derived from sales, so
nothing is duplicated here.
"""
from __future__ import annotations

from django.db import models

from apps.core.models import TenantScopedModel


class Customer(TenantScopedModel):
    class DocumentType(models.TextChoices):
        CC = "CC", "Cédula de ciudadanía"
        CE = "CE", "Cédula de extranjería"
        NIT = "NIT", "NIT"
        PASSPORT = "PASSPORT", "Pasaporte"
        OTHER = "OTHER", "Otro"

    name = models.CharField(max_length=140)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    document_type = models.CharField(
        max_length=10, choices=DocumentType.choices, blank=True, default=""
    )
    document_number = models.CharField(max_length=40, blank=True, default="")
    address = models.CharField(max_length=200, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "customers"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "document_number"],
                condition=~models.Q(document_number=""),
                name="uq_customer_org_document",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "name"]),
            models.Index(fields=["organization", "phone"]),
            models.Index(fields=["organization", "document_number"]),
        ]

    def __str__(self) -> str:
        return self.name
