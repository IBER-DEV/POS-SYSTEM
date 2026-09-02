from rest_framework.routers import DefaultRouter

from .views import RefundViewSet, SaleViewSet

router = DefaultRouter()
router.register("sales", SaleViewSet, basename="sale")
router.register("refunds", RefundViewSet, basename="refund")

urlpatterns = router.urls
