from rest_framework.routers import DefaultRouter

from care_pinelabs.api.viewsets.health_check import HealthCheckViewSet


router = DefaultRouter()

router.register("health_check", HealthCheckViewSet, basename="pinelabs__health_check")

urlpatterns = router.urls
