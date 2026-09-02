"""Ensure the plan catalogue exists.

The same rows are created by migration 0002. This command is the runtime way
to restore them - after a database restore, in a fresh environment, or in
transactional tests, which truncate every table including migration data.

The definitions are deliberately duplicated instead of imported by the
migration: a migration must keep working even when the app code moves on.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.subscriptions.models import Plan

PLANS = [
    {"code": "BASIC", "name": "Basic", "description": "Single store getting started.", "sort_order": 1},
    {"code": "PRO", "name": "Pro", "description": "Growing store with a team.", "sort_order": 2},
    {
        "code": "BUSINESS",
        "name": "Business",
        "description": "Multiple stores and advanced reporting.",
        "sort_order": 3,
    },
]


def seed_plans() -> int:
    created = 0
    for plan in PLANS:
        _, was_created = Plan.objects.update_or_create(code=plan["code"], defaults=plan)
        created += int(was_created)
    return created


class Command(BaseCommand):
    help = "Create or update the subscription plan catalogue."

    def handle(self, *args, **options):
        created = seed_plans()
        self.stdout.write(self.style.SUCCESS(f"Plans ready ({created} created)."))
