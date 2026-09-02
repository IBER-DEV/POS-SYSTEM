from __future__ import annotations

from rest_framework import serializers

from .models import Plan, Subscription


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = [
            "id",
            "code",
            "name",
            "description",
            "monthly_price",
            "yearly_price",
            "currency",
            "max_users",
            "max_locations",
            "max_products",
            "features",
        ]


class SubscriptionSerializer(serializers.ModelSerializer):
    plan = PlanSerializer(read_only=True)
    is_usable = serializers.BooleanField(read_only=True)

    class Meta:
        model = Subscription
        fields = [
            "id",
            "plan",
            "status",
            "billing_cycle",
            "trial_ends_at",
            "current_period_start",
            "current_period_end",
            "is_usable",
        ]
