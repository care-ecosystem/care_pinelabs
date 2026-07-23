from enum import Enum

from rest_framework.exceptions import ValidationError

from care.emr.resources.payment_reconciliation.spec import (
    PaymentReconciliationPaymentMethodOptions as CarePaymentMethod,
)


class PinelabsPaymentMode(str, Enum):
    CARD = "1"
    CASH = "2"
    UPI_SALE = "10"
    UPI_BHARAT_QR = "11"


PAYMENT_METHOD_MAP = {
    CarePaymentMethod.cash: PinelabsPaymentMode.CASH,
    CarePaymentMethod.ccca: PinelabsPaymentMode.CARD,
    CarePaymentMethod.cdac: PinelabsPaymentMode.CARD,
}


def get_payment_method_mapping(value: str) -> PinelabsPaymentMode:
    try:
        return PAYMENT_METHOD_MAP[CarePaymentMethod(value)]
    except (ValueError, KeyError):
        raise ValidationError(f"Unsupported payment method: {value}") from None
