from dataclasses import dataclass
from enum import Enum

from care.emr.resources.payment_reconciliation.spec import (
    PaymentReconciliationPaymentMethodOptions,
)


class PaymentMethod(str, Enum):
    cash = "cash"
    credit_card = "credit_card"
    debit_card = "debit_card"


class PinelabsPaymentMode(str, Enum):
    CARD = "1"
    CASH = "2"
    UPI_SALE = "10"
    UPI_BHARAT_QR = "11"


@dataclass(frozen=True)
class PaymentMethodMapping:
    care: PaymentReconciliationPaymentMethodOptions
    pinelabs: PinelabsPaymentMode


PAYMENT_METHOD_MAP = {
    PaymentMethod.cash: PaymentMethodMapping(
        care=PaymentReconciliationPaymentMethodOptions.cash,
        pinelabs=PinelabsPaymentMode.CASH,
    ),
    PaymentMethod.credit_card: PaymentMethodMapping(
        care=PaymentReconciliationPaymentMethodOptions.ccca,
        pinelabs=PinelabsPaymentMode.CARD,
    ),
    PaymentMethod.debit_card: PaymentMethodMapping(
        care=PaymentReconciliationPaymentMethodOptions.cdac,
        pinelabs=PinelabsPaymentMode.CARD,
    ),
}


class UnsupportedPaymentMethodError(ValueError):
    pass


def get_payment_method_mapping(value: str) -> PaymentMethodMapping:
    try:
        method = PaymentMethod(value)
    except ValueError:
        raise UnsupportedPaymentMethodError(value) from None
    mapping = PAYMENT_METHOD_MAP.get(method)
    if mapping is None:
        raise UnsupportedPaymentMethodError(value)
    return mapping
