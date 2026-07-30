from care.emr.models.device import Device
from care.emr.registries.device_type.device_registry import DeviceTypeBase

from care_pinelabs.api.specs.device import (
    PinelabsDeviceMetadataWriteSpec,
    PinelabsDeviceMetadataReadSpec,
)


class PinelabsDevice(DeviceTypeBase):
    @classmethod
    def handle_create(self, request_data, obj):
        validated_data = PinelabsDeviceMetadataWriteSpec(**request_data)

        obj.metadata = validated_data.model_dump(mode="json")
        obj.save(update_fields=["metadata"])
        return obj

    def handle_update(self, request_data, obj):
        validated_data = PinelabsDeviceMetadataReadSpec(**request_data)

        obj.metadata = validated_data.model_dump(mode="json")
        obj.save(update_fields=["metadata"])
        return obj

    def list(self, obj):
        return self.retrieve(obj)

    def retrieve(self, obj):
        metadata = obj.metadata
        return PinelabsDeviceMetadataReadSpec(**metadata).model_dump(
            mode="json"
        )

    def perform_action(self, obj, action, request):
        raise NotImplementedError("Actions are not implemented")
