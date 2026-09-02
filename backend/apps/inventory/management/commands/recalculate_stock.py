"""Rebuild StockLevel from the inventory ledger.

Doubles as a drift detector: a non-zero `levels_corrected` means something
wrote stock outside InventoryService, which is a bug worth investigating.
"""
from __future__ import annotations

import uuid

from django.core.management.base import BaseCommand
from django.db import models

from apps.core.context import tenant_context
from apps.inventory.services import InventoryService
from apps.organizations.models import Organization


class Command(BaseCommand):
    help = "Recalculate materialised stock levels from the inventory ledger."

    def add_arguments(self, parser):
        parser.add_argument("--organization", help="Organization id or slug. Omit for all tenants.")

    def handle(self, *args, **options):
        organizations = Organization.objects.all()
        identifier = options.get("organization")
        if identifier:
            lookup = models.Q(slug=identifier)
            try:
                lookup |= models.Q(pk=uuid.UUID(identifier))
            except ValueError:
                pass
            organizations = organizations.filter(lookup)

        for organization in organizations:
            with tenant_context(organization.pk):
                result = InventoryService.recalculate(organization=organization)
            style = self.style.WARNING if result["levels_corrected"] else self.style.SUCCESS
            self.stdout.write(style(f"{organization.name}: {result}"))
