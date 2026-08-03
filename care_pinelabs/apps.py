from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

PLUGIN_NAME = "care_pinelabs"


class CarePinelabsConfig(AppConfig):
    name = PLUGIN_NAME
    verbose_name = _("Care Pinelabs")

    def ready(self):
        from care.emr.registries.device_type.device_registry import DeviceTypeRegistry
        from care.security.permissions.base import PermissionController
        from care_pinelabs.api.device import PinelabsDevice
        from care_pinelabs.security.PinelabsPermissions import PinelabsPermissions

        DeviceTypeRegistry.register("pos-terminal", PinelabsDevice)

        PermissionController.register_permission_handler(PinelabsPermissions)

        import care_pinelabs.security.PinelabsAccess  # noqa: F401
