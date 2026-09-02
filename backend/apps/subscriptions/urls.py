from rest_framework.routers import DefaultRouter

from .views import CurrentSubscriptionViewSet, PlanViewSet

router = DefaultRouter()
router.register("plans", PlanViewSet, basename="plan")
router.register("subscription", CurrentSubscriptionViewSet, basename="subscription")

urlpatterns = router.urls
