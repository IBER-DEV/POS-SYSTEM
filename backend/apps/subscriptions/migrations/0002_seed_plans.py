"""Seed the three conceptual plans.

Prices and limits are intentionally left at 0 / unlimited: they are commercial
decisions that have not been made yet, and inventing them would bake fake
requirements into the product. The enforcement machinery (subscriptions.limits)
is already wired, so setting a real limit later is editing a row, not shipping
code.
"""
from django.db import migrations

PLANS = [
    {
        "code": "BASIC",
        "name": "Basic",
        "description": "Single store getting started.",
        "sort_order": 1,
    },
    {
        "code": "PRO",
        "name": "Pro",
        "description": "Growing store with a team.",
        "sort_order": 2,
    },
    {
        "code": "BUSINESS",
        "name": "Business",
        "description": "Multiple stores and advanced reporting.",
        "sort_order": 3,
    },
]


def seed_plans(apps, schema_editor):
    Plan = apps.get_model("subscriptions", "Plan")
    for plan in PLANS:
        Plan.objects.update_or_create(code=plan["code"], defaults=plan)


def unseed_plans(apps, schema_editor):
    Plan = apps.get_model("subscriptions", "Plan")
    Plan.objects.filter(code__in=[p["code"] for p in PLANS]).delete()


class Migration(migrations.Migration):
    dependencies = [("subscriptions", "0001_initial")]

    operations = [migrations.RunPython(seed_plans, unseed_plans)]
