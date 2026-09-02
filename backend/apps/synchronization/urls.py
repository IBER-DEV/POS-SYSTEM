from rest_framework.routers import DefaultRouter

from .views import DeviceViewSet, SyncOperationViewSet, SyncPullViewSet

router = DefaultRouter()
router.register("sync/devices", DeviceViewSet, basename="device")
router.register("sync/operations", SyncOperationViewSet, basename="sync-operation")
router.register("sync/pull", SyncPullViewSet, basename="sync-pull")

urlpatterns = router.urls
