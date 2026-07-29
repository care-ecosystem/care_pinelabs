from care.emr.extensions.base import ExtensionResource, PlugExtension
from care.emr.registries.extensions.registry import ExtensionRegistry

PINELABS_EXTENSION_NAME = "pinelabs"


class PinelabsPaymentReconciliationExtension(PlugExtension):
    resource_type = ExtensionResource.payment_reconciliation
    extension_name = PINELABS_EXTENSION_NAME

ExtensionRegistry.register(PinelabsPaymentReconciliationExtension())
