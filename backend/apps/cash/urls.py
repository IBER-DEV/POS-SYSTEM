from rest_framework.routers import DefaultRouter

from .views import CashMovementViewSet, CashRegisterViewSet, CashSessionViewSet

router = DefaultRouter()
router.register("cash/registers", CashRegisterViewSet, basename="cash-register")
router.register("cash/sessions", CashSessionViewSet, basename="cash-session")
router.register("cash/movements", CashMovementViewSet, basename="cash-movement")

urlpatterns = router.urls
