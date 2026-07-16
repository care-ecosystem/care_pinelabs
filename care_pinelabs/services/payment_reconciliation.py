from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db import transaction
from rest_framework.exceptions import PermissionDenied, ValidationError

from care.emr.models.account import Account
from care.emr.models.invoice import Invoice
from care.emr.models.location import FacilityLocation
from care.emr.models.payment_reconciliation import PaymentReconciliation
from care.emr.resources.account.sync_items import rebalance_account_task
from care.emr.resources.payment_reconciliation.spec import (
    PaymentReconciliationOutcomeOptions,
    PaymentReconciliationStatusOptions,
    PaymentReconciliationWriteSpec,
)
from care.facility.models.facility import Facility
from care.security.authorization.base import AuthorizationController
from care.utils.shortcuts import get_object_or_404
from care.utils.time_util import care_now
from care_pinelabs.models.pinelabs_terminal import PinelabsTerminal
from care_pinelabs.services.specs.plutus_cloud import (
    CancelTransactionResponseData,
    GetStatusResponseData,
    UploadTransactionResponseData,
)

PINELABS_META_KEY = "pinelabs"

PLUTUS_RESPONSE_CODE_APPROVED = 0
PLUTUS_RESPONSE_CODE_VOIDED = 1008
PLUTUS_RESPONSE_CODE_UPLOADED = 1001

PAISE_PER_RUPEE = 100


def rupees_to_paise(amount: Decimal | int | float | None) -> int:
    if amount is None:
        return 0
    return int(Decimal(amount) * PAISE_PER_RUPEE)


def _metainfo_to_dict(items) -> dict[str, str | None]:
    if not items:
        return {}
    return {item.Tag: item.Value for item in items}


def build_upload_meta(
    *,
    terminal: PinelabsTerminal,
    transaction_number: str,
    payment_mode: str,
    response: UploadTransactionResponseData,
) -> dict[str, Any]:
    return {
        PINELABS_META_KEY: {
            "terminal_id": str(terminal.external_id),
            "transaction_number": transaction_number,
            "payment_mode": payment_mode,
            "transaction_reference_id": response.transaction_reference_id,
            "upload": {
                "response_code": response.response_code,
                "response_message": response.response_message,
                "additional_info": _metainfo_to_dict(response.additional_info),
            },
        }
    }


def build_status_meta(
    existing_meta: dict[str, Any], response: GetStatusResponseData
) -> dict[str, Any]:
    pinelabs_meta = dict(existing_meta.get(PINELABS_META_KEY, {}))
    pinelabs_meta["status"] = {
        "response_code": response.response_code,
        "response_message": response.response_message,
        "transaction_data": _metainfo_to_dict(response.transaction_data),
    }
    return {PINELABS_META_KEY: pinelabs_meta}


def build_cancel_meta(
    existing_meta: dict[str, Any], response: CancelTransactionResponseData
) -> dict[str, Any]:
    pinelabs_meta = dict(existing_meta.get(PINELABS_META_KEY, {}))
    pinelabs_meta["cancel"] = {
        "response_code": response.response_code,
        "response_message": response.response_message,
    }
    return {PINELABS_META_KEY: pinelabs_meta}


def resolve_status_outcome(
    response: GetStatusResponseData,
) -> tuple[PaymentReconciliationStatusOptions, PaymentReconciliationOutcomeOptions]:
    """Map a Plutus status response to a (status, outcome) tuple.

    Treats the response as terminal only when Plutus returns the well-known
    APPROVED (`0`) or UPLOADED (`1001`) codes.
        - APPROVED code indicates that the transaction was approved and the funds were transferred.
        - UPLOADED code indicates that the transaction was uploaded to the Plutus system and is pending approval.
        - Every other non-zero code is treated as error.
    """
    code = response.response_code
    if code == PLUTUS_RESPONSE_CODE_APPROVED:
        return (
            PaymentReconciliationStatusOptions.active,
            PaymentReconciliationOutcomeOptions.complete,
        )
    if code == PLUTUS_RESPONSE_CODE_UPLOADED:
        return (
            PaymentReconciliationStatusOptions.draft,
            PaymentReconciliationOutcomeOptions.queued,
        )

    return (
        PaymentReconciliationStatusOptions.cancelled,
        PaymentReconciliationOutcomeOptions.error,
    )


def apply_status_to_reconciliation(
    instance: PaymentReconciliation, response: GetStatusResponseData
) -> bool:
    new_status, new_outcome = resolve_status_outcome(response)
    instance.meta = {
        **(instance.meta or {}),
        **build_status_meta(instance.meta or {}, response),
    }
    transaction_data = _metainfo_to_dict(response.transaction_data)

    instance.outcome = new_outcome.value
    instance.status = new_status.value
    if rrn := transaction_data.get("RRN"):
        instance.reference_number = str(rrn)
    if approval_code := transaction_data.get("ApprovalCode"):
        instance.authorization = str(approval_code)
    if new_outcome == PaymentReconciliationOutcomeOptions.complete:
        instance.payment_datetime = care_now()

    instance.save()
    if new_outcome == PaymentReconciliationOutcomeOptions.complete:
        rebalance_account_task(instance.account_id)

    return new_outcome != PaymentReconciliationOutcomeOptions.queued


def authorize_payment_reconciliation_create(
    spec: PaymentReconciliationWriteSpec, facility: Facility, user
) -> Account:
    account = get_object_or_404(Account, external_id=spec.account)
    if not AuthorizationController.call(
        "can_write_payment_reconciliation_in_facility", user, facility
    ):
        raise PermissionDenied("Cannot write payment reconciliation")
    if account.facility != facility:
        raise ValidationError("Account is not associated with the facility")
    if spec.location:
        location = get_object_or_404(FacilityLocation, external_id=spec.location)
        if location.facility != facility:
            raise ValidationError("Location is not associated with the facility")
        if not AuthorizationController.call(
            "can_list_facility_location_obj", user, facility, location
        ):
            raise PermissionDenied("You do not have permission to given location")
    if spec.target_invoice:
        invoice = get_object_or_404(
            Invoice, external_id=spec.target_invoice, account=account
        )
        if invoice.facility != facility:
            raise ValidationError("Invoice is not associated with the facility")
    return account


def create_payment_reconciliation(
    spec: PaymentReconciliationWriteSpec,
    *,
    facility: Facility,
    user,
    meta: dict | None = None,
) -> PaymentReconciliation:
    authorize_payment_reconciliation_create(spec, facility, user)
    instance = spec.de_serialize()
    instance.facility = facility
    instance.created_by = user
    instance.updated_by = user
    if meta:
        instance.meta = {**(instance.meta or {}), **meta}
    with transaction.atomic():
        instance.save()
    rebalance_account_task(instance.account_id)
    return instance


def authorize_payment_reconciliation_cancel(
    instance: PaymentReconciliation, user
) -> None:
    if instance.created_date >= care_now() - timedelta(
        minutes=settings.PAYMENT_RECONCILIATION_FREE_CANCEL_PERIOD_MINUTES
    ):
        if not AuthorizationController.call(
            "can_write_payment_reconciliation_in_facility", user, instance.facility
        ):
            raise PermissionDenied("Cannot update payment reconciliation")
        return
    if not AuthorizationController.call(
        "can_destroy_payment_reconciliation_in_facility", user, instance.facility
    ):
        raise PermissionDenied(
            "User does not have permission to cancel payment reconciliation"
        )


def cancel_payment_reconciliation(
    instance: PaymentReconciliation,
    *,
    user,
    status: PaymentReconciliationStatusOptions,
    meta: dict | None = None,
) -> PaymentReconciliation:
    if status not in (
        PaymentReconciliationStatusOptions.cancelled,
        PaymentReconciliationStatusOptions.entered_in_error,
    ):
        raise ValidationError("Invalid reason")
    authorize_payment_reconciliation_cancel(instance, user)
    instance.status = status.value
    instance.updated_by = user
    if meta:
        instance.meta = {**(instance.meta or {}), **meta}
    instance.save()
    rebalance_account_task(instance.account_id)
    return instance


def authorize_payment_reconciliation_refresh(
    instance: PaymentReconciliation, user
) -> None:
    """Check if user has permission to refresh payment reconciliation status."""
    if not AuthorizationController.call(
        "can_write_payment_reconciliation_in_facility", user, instance.facility
    ):
        raise PermissionDenied("Cannot update payment reconciliation status")


def refresh_payment_reconciliation_status(
    instance: PaymentReconciliation,
    *,
    user,
) -> tuple[PaymentReconciliation, bool]:
    """
    Refresh payment reconciliation status from Pine Labs.

    Returns tuple of (reconciliation, status_changed)
    where status_changed is True if status was updated.
    """
    from care_pinelabs.models.pinelabs_terminal import PinelabsTerminal
    from care_pinelabs.services.plutus_cloud import PlutusCloudService
    from care_pinelabs.services.specs.plutus_cloud import GetStatusRequestData

    # 1. Authorize
    authorize_payment_reconciliation_refresh(instance, user)

    # 2. Extract Pine Labs metadata
    pinelabs_meta = (instance.meta or {}).get(PINELABS_META_KEY, {})
    terminal_external_id = pinelabs_meta.get("terminal_id")
    transaction_reference_id = pinelabs_meta.get("transaction_reference_id")

    if not terminal_external_id or transaction_reference_id is None:
        raise ValidationError("PaymentReconciliation has no pinelabs metadata")

    # 3. Get terminal configuration
    terminal = get_object_or_404(PinelabsTerminal, external_id=terminal_external_id)

    # 4. Call Pine Labs GetStatus API
    plutus_response = PlutusCloudService().get_status(
        GetStatusRequestData(
            plutus_transaction_reference_id=str(transaction_reference_id),
            client_id=terminal.client_id,
            store_id=terminal.store_id,
        )
    )

    # 5. Check if status has changed
    instance.refresh_from_db()
    current_pinelabs_meta = (instance.meta or {}).get(PINELABS_META_KEY, {})
    current_status_meta = current_pinelabs_meta.get("status", {})
    current_response_code = current_status_meta.get("response_code")

    status_changed = current_response_code != plutus_response.response_code

    # 6. Apply status to reconciliation only if changed
    if status_changed:
        apply_status_to_reconciliation(instance, plutus_response)

    return instance, status_changed
