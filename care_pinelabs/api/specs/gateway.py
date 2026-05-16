from pydantic import UUID4, BaseModel, model_validator

from care.emr.resources.payment_reconciliation.spec import (
    PaymentReconciliationOutcomeOptions,
    PaymentReconciliationStatusOptions,
    PaymentReconciliationWriteSpec,
)
from care_pinelabs.services.specs.plutus_cloud import AllowedPaymentMode


class UploadTransactionSpec(PaymentReconciliationWriteSpec):
    """
    Pinelabs upload-transaction specification.

    Inherits the payment reconciliation write spec so a single payload drives
    both the Plutus upload call and the resulting PaymentReconciliation record.
    `status` and `outcome` are pinned server-side to `draft` and `queued` respectively, any client-supplied values are ignored.
    """

    terminal: UUID4
    payment_mode: AllowedPaymentMode = AllowedPaymentMode.UPI

    @model_validator(mode="before")
    @classmethod
    def _force_status_and_outcome(cls, data):
        if isinstance(data, dict):
            return {
                **data,
                "status": PaymentReconciliationStatusOptions.draft.value,
                "outcome": PaymentReconciliationOutcomeOptions.queued.value,
            }
        return data


class TransactionStatusSpec(BaseModel):
    payment_reconciliation: UUID4


class CancelTransactionSpec(BaseModel):
    payment_reconciliation: UUID4
