from datetime import datetime
from decimal import Decimal

from pydantic import UUID4

from care.emr.resources.base import EMRResource
from care.emr.resources.payment_reconciliation.spec import (
    PaymentReconciliationOutcomeOptions,
)
from care_pinelabs.models.pinelabs_transaction import (
    PinelabsTransaction,
    PinelabsTransactionStatus,
)


class PinelabsTransactionReadSpec(EMRResource):
    __model__ = PinelabsTransaction
    __exclude__ = ["terminal", "account", "invoice", "payment_reconciliation"]

    id: UUID4 | None = None
    terminal: UUID4 | None = None
    transaction_number: str
    transaction_id: str | None = None
    payment_reconciliation: UUID4 | None = None
    method: str
    location: UUID4 | None = None
    amount: Decimal | None = None
    account: dict | None = None
    target_invoice: dict | None = None
    reference_number: str | None = None
    tendered_amount: Decimal | None = None
    status: PinelabsTransactionStatus | None = None
    created_by: dict | None = None
    created_date: datetime
    modified_date: datetime

    @classmethod
    def perform_extra_serialization(cls, mapping, obj):
        mapping["id"] = obj.external_id
        mapping["terminal"] = obj.terminal.external_id
        mapping["method"] = obj.payment_mode
        mapping["transaction_id"] = obj.plutus_transaction_reference_id

        reconciliation = obj.payment_reconciliation
        mapping["payment_reconciliation"] = (
            reconciliation.external_id if reconciliation else None
        )
        mapping["location"] = (
            reconciliation.location.external_id
            if reconciliation and reconciliation.location
            else None
        )
        mapping["amount"] = reconciliation.amount if reconciliation else None
        mapping["account"] = (
            {
                "id": reconciliation.account.external_id,
                "name": reconciliation.account.name,
            }
            if reconciliation and reconciliation.account
            else None
        )
        mapping["target_invoice"] = (
            {
                "id": reconciliation.target_invoice.external_id,
                "number": reconciliation.target_invoice.number,
            }
            if reconciliation and reconciliation.target_invoice
            else None
        )
        mapping["reference_number"] = (
            reconciliation.reference_number if reconciliation else None
        )
        mapping["tendered_amount"] = (
            reconciliation.tendered_amount if reconciliation else None
        )
        mapping["status"] = reconciliation.outcome if reconciliation else None
        mapping["created_by"] = None
        if reconciliation and reconciliation.created_by_id:
            from care.emr.resources.base import model_from_cache
            from care.emr.resources.user.spec import UserSpec

            mapping["created_by"] = model_from_cache(
                UserSpec, id=reconciliation.created_by_id
            )
