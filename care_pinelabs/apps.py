import sys

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

PLUGIN_NAME = "care_pinelabs"

BUILD_TIME_COMMANDS = {
    "collectstatic",
    "makemigrations",
    "migrate",
    "compilemessages",
    "makemessages",
    "spectacular",
    "test",
}


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

        if len(sys.argv) > 1 and sys.argv[1] in BUILD_TIME_COMMANDS:
            return

        from care_pinelabs.settings import plugin_settings

        plugin_settings.validate()
