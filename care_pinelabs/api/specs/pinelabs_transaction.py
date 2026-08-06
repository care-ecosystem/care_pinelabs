from datetime import datetime

from pydantic import UUID4

from care.emr.resources.base import EMRResource
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
    status: PinelabsTransactionStatus
    method: str
    location: UUID4 | None = None
    created_by: dict | None = None
    created_date: datetime
    modified_date: datetime

    @classmethod
    def perform_extra_serialization(cls, mapping, obj):
        mapping["id"] = obj.external_id
        mapping["terminal"] = obj.terminal.external_id
        mapping["method"] = obj.payment_mode

        reconciliation = obj.payment_reconciliation
        mapping["location"] = (
            reconciliation.location.external_id
            if reconciliation and reconciliation.location
            else None
        )
        mapping["created_by"] = None
        if reconciliation and reconciliation.created_by_id:
            from care.emr.resources.base import model_from_cache
            from care.emr.resources.user.spec import UserSpec

            mapping["created_by"] = model_from_cache(
                UserSpec, id=reconciliation.created_by_id
            )
