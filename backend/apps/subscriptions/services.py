from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from .models import Plan, Subscription

TRIAL_DAYS = 14


def start_trial_subscription(*, organization, plan_code: str = Plan.Code.BASIC) -> Subscription:
    plan = Plan.objects.filter(code=plan_code).first() or Plan.objects.order_by("sort_order").first()
    if plan is None:
        raise RuntimeError("No subscription plans are configured. Run `manage.py migrate`.")

    now = timezone.now()
    return Subscription.objects.create(
        organization=organization,
        plan=plan,
        status=Subscription.Status.TRIAL,
        trial_ends_at=now + timedelta(days=TRIAL_DAYS),
        current_period_start=now,
        current_period_end=now + timedelta(days=TRIAL_DAYS),
    )
