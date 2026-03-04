from rest_framework import serializers

from care_pinelabs.models.pinelabs_terminal import PinelabsTerminal
from care_pinelabs.services.specs.plutus_cloud_uat import AllowedPaymentMode


class UploadTransactionSerializer(serializers.Serializer):
    terminal = serializers.SlugRelatedField(
        slug_field="external_id",
        queryset=PinelabsTerminal.objects.all(),
        required=True,
    )
    payment_mode = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in AllowedPaymentMode],
        default=AllowedPaymentMode.UPI.value,
    )
    amount = serializers.IntegerField(required=True)


class TransactionStatusSerializer(serializers.Serializer):
    terminal = serializers.SlugRelatedField(
        slug_field="external_id",
        queryset=PinelabsTerminal.objects.all(),
        required=True,
    )
    transaction_reference_id = serializers.CharField(required=True)


class CancelTransactionSerializer(serializers.Serializer):
    terminal = serializers.SlugRelatedField(
        slug_field="external_id",
        queryset=PinelabsTerminal.objects.all(),
        required=True,
    )
    transaction_reference_id = serializers.CharField(required=True)
    amount = serializers.IntegerField(required=True)
