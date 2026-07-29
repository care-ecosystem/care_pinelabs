from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

PLUGIN_NAME = "care_pinelabs"


class CarePinelabsConfig(AppConfig):
    name = PLUGIN_NAME
    verbose_name = _("Care Pinelabs")

    def ready(self):
        from care.emr.registries.device_type.device_registry import DeviceTypeRegistry
        from care_pinelabs.api.device import PinelabsDevice

        DeviceTypeRegistry.register("pinelabs", PinelabsDevice)
