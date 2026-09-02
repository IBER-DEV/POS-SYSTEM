from rest_framework.routers import DefaultRouter

from .views import (
    InitialStockViewSet,
    InventoryAdjustmentViewSet,
    InventoryMovementViewSet,
    StockDiscrepancyViewSet,
    StockLevelViewSet,
)

router = DefaultRouter()
router.register("inventory/stock", StockLevelViewSet, basename="stock-level")
router.register("inventory/movements", InventoryMovementViewSet, basename="inventory-movement")
router.register("inventory/adjustments", InventoryAdjustmentViewSet, basename="inventory-adjustment")
router.register("inventory/initial-stock", InitialStockViewSet, basename="inventory-initial-stock")
router.register("inventory/discrepancies", StockDiscrepancyViewSet, basename="stock-discrepancy")

urlpatterns = router.urls
