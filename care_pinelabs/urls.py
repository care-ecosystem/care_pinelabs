from rest_framework.routers import DefaultRouter

from care_pinelabs.api.viewsets.gateway import GatewayViewSet
from care_pinelabs.api.viewsets.health_check import HealthCheckViewSet
from care_pinelabs.api.viewsets.pinelabs_config import PinelabsConfigViewSet
from care_pinelabs.api.viewsets.pinelabs_terminal import PinelabsTerminalViewSet
from care_pinelabs.api.viewsets.pinelabs_transaction import PinelabsTransactionViewSet

router = DefaultRouter()

router.register("health_check", HealthCheckViewSet, basename="pinelabs__health_check")
router.register(
    "pinelabs_terminal", PinelabsTerminalViewSet, basename="pinelabs__pinelabs_terminal"
)
router.register(
    "pinelabs_config", PinelabsConfigViewSet, basename="pinelabs__pinelabs_config"
)
router.register(
    "pinelabs_transactions",
    PinelabsTransactionViewSet,
    basename="pinelabs__pinelabs_transaction",
)
router.register("gateway", GatewayViewSet, basename="pinelabs__gateway")

urlpatterns = router.urls
