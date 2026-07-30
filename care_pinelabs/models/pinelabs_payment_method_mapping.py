from django.db import models

from care.emr.models.base import BaseModel
from care.emr.resources.payment_reconciliation.spec import (
    PaymentReconciliationPaymentMethodOptions as CarePaymentMethod,
)
from care_pinelabs.models.pinelabs_config import PinelabsConfig


class PinelabsPaymentModeChoices(models.TextChoices):
    CARD = "1", "Card"
    CASH = "2", "Cash"
    UPI_SALE = "10", "UPI Sale"
    UPI_BHARAT_QR = "11", "UPI Bharat QR"


class PinelabsPaymentMethodMapping(BaseModel):
    config = models.ForeignKey(
        PinelabsConfig,
        on_delete=models.CASCADE,
        related_name="payment_method_mappings",
    )
    care_method = models.CharField(max_length=255, choices=CarePaymentMethod)
    pinelabs_method = models.CharField(
        max_length=255, choices=PinelabsPaymentModeChoices.choices
    )
    is_default = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["config", "pinelabs_method"],
                condition=models.Q(deleted=False),
                name="unique_care_method_per_config",
            ),
            models.UniqueConstraint(
                fields=["config"],
                condition=models.Q(is_default=True, deleted=False),
                name="unique_default_payment_method_per_config",
            ),
        ]
