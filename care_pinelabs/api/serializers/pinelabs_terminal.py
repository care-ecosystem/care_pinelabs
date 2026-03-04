from rest_framework import serializers

from care.facility.models import Facility
from care_pinelabs.models.pinelabs_terminal import PinelabsTerminal


class PinelabsTerminalSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="external_id", read_only=True)
    facility_id = serializers.UUIDField()
    client_id = serializers.CharField(max_length=255)
    store_id = serializers.CharField(max_length=255)
    name = serializers.CharField(max_length=255)
    is_active = serializers.BooleanField(default=True)
    created_date = serializers.DateTimeField(read_only=True)
    modified_date = serializers.DateTimeField(read_only=True)

    class Meta:
        model = PinelabsTerminal
        exclude = ("deleted", "facility")

    def to_representation(self, instance):
        data = super().to_representation(instance)

        if instance.facility:
            data["facility_id"] = instance.facility.external_id
        return data

    def validate_facility_id(self, value):
        """Validate that the facility exists and is accessible."""
        try:
            Facility.objects.get(external_id=value)
            return value
        except Facility.DoesNotExist as e:
            error_msg = f"Facility with external_id {value} does not exist."
            raise serializers.ValidationError(error_msg) from e

    def create(self, validated_data):
        facility_id = validated_data.pop("facility_id")
        facility = Facility.objects.get(external_id=facility_id)
        validated_data["facility"] = facility
        return super().create(validated_data)

    def update(self, instance, validated_data):
        facility_id = validated_data.pop("facility_id", None)
        if facility_id:
            facility = Facility.objects.get(external_id=facility_id)
            validated_data["facility"] = facility
        return super().update(instance, validated_data)
