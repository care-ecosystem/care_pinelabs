import math

from celery import shared_task
from celery.utils.log import get_task_logger
from django.db import transaction

from care.emr.models.payment_reconciliation import PaymentReconciliation
from care.emr.resources.payment_reconciliation.spec import (
    PaymentReconciliationOutcomeOptions,
    PaymentReconciliationStatusOptions,
)
from care_pinelabs.models.pinelabs_pos_terminal import PinelabsPosTerminal
from care_pinelabs.services.payment_reconciliation import (
    PINELABS_META_KEY,
    apply_status_to_reconciliation,
)
from care_pinelabs.services.plutus_cloud import PlutusCloudService
from care_pinelabs.services.specs.plutus_cloud import GetStatusRequestData
from care_pinelabs.settings import plugin_settings

logger = get_task_logger(__name__)


def _poll_interval_seconds() -> int:
    return plugin_settings.PINELABS_POLL_INTERVAL_SECONDS


def _max_poll_attempts() -> int:
    """
    Number of poll attempts that cover the Plutus auto-cancel window plus a buffer.
    """

    seconds_per_minute = 60
    total_window_seconds = (
        plugin_settings.PINELABS_AUTO_CANCEL_DURATION_MINUTES * seconds_per_minute
        + plugin_settings.PINELABS_POLL_BUFFER_SECONDS
    )

    return math.ceil(total_window_seconds / _poll_interval_seconds())


@shared_task(
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3},
    expires=60 * 60,
)
def poll_pinelabs_transaction_status(
    payment_reconciliation_id: int,
    attempt: int = 1,
) -> None:
    """
    Poll Plutus for the status of an in-flight transaction.

    Self-reschedules every ``PINELABS_POLL_INTERVAL_SECONDS`` until the
    reconciliation reaches a terminal outcome or the polling window
    (Plutus auto-cancel duration + buffer) is exhausted, in which case the
    reconciliation is left in ``queued``.
    """

    instance = PaymentReconciliation.objects.filter(
        id=payment_reconciliation_id
    ).first()
    if instance is None:
        logger.warning(
            "PaymentReconciliation %s not found for pinelabs polling",
            payment_reconciliation_id,
        )
        return
    if instance.outcome != PaymentReconciliationOutcomeOptions.queued.value:
        return

    pinelabs_meta = (instance.meta or {}).get(PINELABS_META_KEY, {})
    terminal_external_id = pinelabs_meta.get("terminal_id")
    transaction_reference_id = pinelabs_meta.get("transaction_reference_id")
    if not terminal_external_id or transaction_reference_id is None:
        logger.error(
            "PaymentReconciliation %s is missing pinelabs metadata",
            payment_reconciliation_id,
        )
        return

    terminal = (
        PinelabsPosTerminal.objects.filter(
            external_id=terminal_external_id,
            device__deleted=False,
            config__deleted=False,
        )
        .select_related("device", "config")
        .first()
    )
    if terminal is None:
        logger.error(
            "Pinelabs terminal %s for PaymentReconciliation %s not found",
            terminal_external_id,
            payment_reconciliation_id,
        )
        if attempt >= _max_poll_attempts():
            return
        poll_pinelabs_transaction_status.apply_async(
            kwargs={
                "payment_reconciliation_id": payment_reconciliation_id,
                "attempt": attempt + 1,
            },
            countdown=_poll_interval_seconds(),
        )
        return

    response = PlutusCloudService().get_status(
        GetStatusRequestData(
            plutus_transaction_reference_id=str(transaction_reference_id),
            merchant_id=terminal.config.pinelabs_merchant_id,
            security_token=terminal.config.pinelabs_security_token,
            client_id=terminal.device.metadata["client_id"],
            store_id=terminal.device.metadata["store_id"],
        )
    )

    finalized = apply_status_to_reconciliation(instance, response)
    if finalized:
        return

    if attempt >= _max_poll_attempts():
        logger.info(
            "Stopped polling PaymentReconciliation %s after %s attempts",
            payment_reconciliation_id,
            attempt,
        )
        instance.status = PaymentReconciliationStatusOptions.cancelled.value
        instance.outcome = PaymentReconciliationOutcomeOptions.error.value
        with transaction.atomic():
            instance.save(update_fields=["status", "outcome", "modified_date"])
            if hasattr(instance, "terminal_transaction") and instance.terminal_transaction:
                instance.terminal_transaction.mark_timed_out()
        return

    poll_pinelabs_transaction_status.apply_async(
        kwargs={
            "payment_reconciliation_id": payment_reconciliation_id,
            "attempt": attempt + 1,
        },
        countdown=_poll_interval_seconds(),
    )
