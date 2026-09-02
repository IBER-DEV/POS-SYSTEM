from rest_framework.routers import DefaultRouter

from .views import CurrentOrganizationViewSet, LocationViewSet

router = DefaultRouter()
router.register("organization", CurrentOrganizationViewSet, basename="organization")
router.register("locations", LocationViewSet, basename="location")

urlpatterns = router.urls
