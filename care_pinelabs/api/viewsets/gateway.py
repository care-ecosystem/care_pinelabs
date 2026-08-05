import logging

from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from care.security.authorization.base import AuthorizationController

from care.emr.models.payment_reconciliation import PaymentReconciliation
from care.emr.resources.payment_reconciliation.spec import (
    PaymentReconciliationOutcomeOptions,
    PaymentReconciliationReadSpec,
    PaymentReconciliationStatusOptions,
)
from care.utils.shortcuts import get_object_or_404
from care_pinelabs.api.exceptions import pinelabs_exception_handler
from care_pinelabs.api.specs.gateway import (
    CancelTransactionSpec,
    TransactionStatusSpec,
    UploadTransactionSpec,
)
from care_pinelabs.models.pinelabs_pos_terminal import PinelabsPosTerminal
from care_pinelabs.services.payment_reconciliation import (
    PINELABS_META_KEY,
    PLUTUS_RESPONSE_CODE_APPROVED,
    authorize_payment_reconciliation_cancel,
    authorize_payment_reconciliation_create,
    authorize_payment_reconciliation_read,
    build_cancel_meta,
    cancel_payment_reconciliation,
    create_payment_reconciliation,
    refresh_payment_reconciliation_status,
    rupees_to_paise,
    validate_upload_business_rules,
)
from care_pinelabs.services.plutus_cloud import PlutusCloudService
from care_pinelabs.services.specs.plutus_cloud import (
    CancelTransactionRequestData,
    UploadTransactionRequestData,
)
from care_pinelabs.services.terminal_transaction import acquire_terminal_lock
from care_pinelabs.services.transaction_number import generate_transaction_number
from care_pinelabs.settings import plugin_settings
from care_pinelabs.tasks.poll_transaction_status import poll_pinelabs_transaction_status

logger = logging.getLogger(__name__)


@extend_schema(tags=["Pinelabs: Gateway"])
class GatewayViewSet(GenericViewSet):
    permission_classes = (IsAuthenticated,)

    def get_exception_handler(self):
        return pinelabs_exception_handler

    def _get_terminal(self, external_id) -> PinelabsPosTerminal:
        return get_object_or_404(
            PinelabsPosTerminal.objects.select_related(
                "config__facility", "device"
            ).filter(device__deleted=False, config__deleted=False),
            external_id=external_id,
        )

    def _get_reconciliation(self, external_id) -> PaymentReconciliation:
        return get_object_or_404(PaymentReconciliation, external_id=external_id)

    @staticmethod
    def _serialize_reconciliation(instance: PaymentReconciliation) -> dict:
        return PaymentReconciliationReadSpec.serialize(instance).to_json()

    @staticmethod
    def _serialize_reconciliation_with_meta(instance: PaymentReconciliation) -> dict:
        """Serialize reconciliation including meta field for Pine Labs endpoints."""
        serialized = PaymentReconciliationReadSpec.serialize(instance).to_json()
        # Explicitly include meta field for Pine Labs gateway endpoints
        serialized["meta"] = instance.meta or {}
        return serialized

    @staticmethod
    def _extract_validation_error_message(e: ValidationError) -> str:
        """Extract clean error message from DRF ValidationError."""
        if isinstance(e.detail, list):
            return str(e.detail[0]) if e.detail else "Validation error"
        elif isinstance(e.detail, dict):
            return str(next(iter(e.detail.values()))) if e.detail else "Validation error"
        else:
            return str(e.detail)

    @extend_schema(request=UploadTransactionSpec)
    @action(detail=False, methods=["POST"])
    def upload_transaction(self, request):
        """
        Upload transaction to Pine Labs terminal.

        Clean flow:
        1. Get terminal
        2. Authorize (permissions + get account/invoice)
        3. Validate business rules (terminal active, invoice balanced, amount)
        4. Generate transaction number
        5. Acquire terminal lock
        6. Create payment reconciliation
        7. Upload to Pine Labs
        8. On success: mark uploaded
        9. Start polling
        """
        request_data = UploadTransactionSpec.model_validate(request.data)
        terminal = self._get_terminal(request_data.terminal)
        user = request.user

        # Step 1: Authorize and get account/invoice (single fetch)
        try:
            account, invoice = authorize_payment_reconciliation_create(
                request_data, terminal.config.facility, user
            )
        except (ValidationError, PermissionDenied) as e:
            logger.warning("Authorization failed: %s", str(e))
            if isinstance(e, ValidationError):
                return Response(
                    {"errors": [{"type": "validation_error", "msg": self._extract_validation_error_message(e)}]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            else:
                return Response(
                    {"errors": [{"type": "permission_denied", "msg": str(e)}]},
                    status=status.HTTP_403_FORBIDDEN,
                )

        # Step 2: Validate business rules
        try:
            validate_upload_business_rules(terminal, invoice, request_data.amount)
        except ValidationError as e:
            logger.warning("Business validation failed: %s", str(e))
            return Response(
                {"errors": [{"type": "validation_error", "msg": self._extract_validation_error_message(e)}]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Generate transaction number
        transaction_number = generate_transaction_number(account=account, invoice=invoice)

        logger.info(
            "Generated transaction number: %s (account=%s, invoice=%s)",
            transaction_number,
            account.id,
            invoice.number if invoice else None,
        )

        try:
            with transaction.atomic():
                # Acquire terminal lock (blocks device with "started" status)
                terminal_txn = acquire_terminal_lock(
                    terminal=terminal,
                    account=account,
                    invoice=invoice,
                    transaction_number=transaction_number,
                    payment_mode=request_data.payment_mode.value,
                )

                logger.info(
                    "Terminal lock acquired: %s (terminal=%s, status=%s)",
                    transaction_number,
                    terminal.device.registered_name,
                    terminal_txn.status,
                )

                # Create payment reconciliation (draft, initiated)
                reconciliation = create_payment_reconciliation(
                    request_data,
                    facility=terminal.config.facility,
                    user=user,
                    meta={
                        "pinelabs": {
                            "terminal_id": str(terminal.external_id),
                            "transaction_number": transaction_number,
                            "payment_mode": request_data.payment_mode.value,
                        }
                    },
                )

                # Link terminal transaction to payment
                terminal_txn.payment_reconciliation = reconciliation
                terminal_txn.save(update_fields=["payment_reconciliation", "modified_date"])

                logger.info(
                    "Payment reconciliation created: %s (status=%s, outcome=%s)",
                    reconciliation.external_id,
                    reconciliation.status,
                    reconciliation.outcome,
                )

                # Upload to Pine Labs
                try:
                    plutus_response = PlutusCloudService().upload_transaction(
                        UploadTransactionRequestData(
                            transaction_number=transaction_number,
                            sequence_number=1,
                            allowed_payment_mode=request_data.payment_mode,
                            amount=rupees_to_paise(request_data.amount),
                            user_id=user.username,
                            merchant_id=terminal.config.pinelabs_merchant_id,
                            security_token=terminal.config.pinelabs_security_token,
                            client_id=terminal.device.metadata["client_id"],
                            store_id=terminal.device.metadata["store_id"],
                            auto_cancel_duration_in_minutes=plugin_settings.PINELABS_AUTO_CANCEL_DURATION_MINUTES,
                        )
                    )

                    logger.info(
                        "Pine Labs upload response: code=%s, message=%s, PTRID=%s",
                        plutus_response.response_code,
                        plutus_response.response_message,
                        plutus_response.transaction_reference_id,
                    )

                    # Check if upload succeeded
                    if (
                        plutus_response.response_code != PLUTUS_RESPONSE_CODE_APPROVED
                        or plutus_response.transaction_reference_id is None
                    ):
                        # Upload failed - mark terminal transaction as completed
                        terminal_txn.mark_completed()

                        # Mark payment reconciliation as ERROR
                        reconciliation.status = PaymentReconciliationStatusOptions.cancelled.value
                        reconciliation.outcome = PaymentReconciliationOutcomeOptions.error.value
                        reconciliation.meta["pinelabs"]["upload"] = {
                            "response_code": plutus_response.response_code,
                            "response_message": plutus_response.response_message,
                            "failed_at": timezone.now().isoformat(),
                        }
                        reconciliation.save(update_fields=["status", "outcome", "meta", "modified_date"])

                        logger.warning(
                            "Pine Labs upload failed: %s (code=%s, payment marked as error)",
                            plutus_response.response_message,
                            plutus_response.response_code,
                        )

                        return Response(
                            {
                                "errors": [
                                    {
                                        "type": "pinelabs_upload_failed",
                                        "msg": plutus_response.response_message,
                                        "code": plutus_response.response_code,
                                    }
                                ]
                            },
                            status=status.HTTP_400_BAD_REQUEST,
                        )

                    # On success - mark uploaded and update to "in_progress"
                    ptrid = str(plutus_response.transaction_reference_id)
                    terminal_txn.mark_uploaded(ptrid)

                    logger.info(
                        "Terminal transaction marked uploaded: %s (PTRID=%s, status=%s)",
                        transaction_number,
                        ptrid,
                        terminal_txn.status,
                    )

                    # Update payment reconciliation
                    reconciliation.meta["pinelabs"]["transaction_reference_id"] = ptrid
                    reconciliation.meta["pinelabs"]["upload"] = {
                        "response_code": plutus_response.response_code,
                        "response_message": plutus_response.response_message,
                        "uploaded_at": timezone.now().isoformat(),
                    }
                    reconciliation.save(update_fields=["meta", "modified_date"])

                    logger.info(
                        "Payment reconciliation updated: %s (outcome=%s)",
                        reconciliation.external_id,
                        reconciliation.outcome,
                    )

                except Exception as e:
                    logger.error("Pine Labs API call failed: %s", str(e), exc_info=True)
                    # Mark terminal transaction as completed so terminal is freed
                    terminal_txn.mark_completed()

                    # Mark payment reconciliation as ERROR
                    reconciliation.status = PaymentReconciliationStatusOptions.cancelled.value
                    reconciliation.outcome = PaymentReconciliationOutcomeOptions.error.value
                    reconciliation.meta["pinelabs"]["upload_error"] = {
                        "error": str(e),
                        "failed_at": timezone.now().isoformat(),
                    }
                    reconciliation.save(update_fields=["status", "outcome", "meta", "modified_date"])

                    raise

                # Start polling (normal flow)
                transaction.on_commit(
                    lambda: poll_pinelabs_transaction_status.delay(
                        payment_reconciliation_id=reconciliation.id
                    )
                )

                logger.info(
                    "Polling task scheduled for payment: %s", reconciliation.external_id
                )

                return Response(
                    self._serialize_reconciliation(reconciliation),
                    status=status.HTTP_201_CREATED,
                )

        except ValidationError as e:
            # Terminal busy / invoice busy / account busy / duplicate transaction
            logger.warning("Terminal lock acquisition failed: %s", str(e))
            return Response(
                {"errors": [{"type": "validation_error", "msg": self._extract_validation_error_message(e)}]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        except Exception as e:
            logger.error("Unexpected error in upload_transaction: %s", str(e), exc_info=True)
            raise

    @extend_schema(request=TransactionStatusSpec)
    @action(detail=False, methods=["POST"])
    def transaction_status(self, request):
        # Validate request data first
        request_data = TransactionStatusSpec.model_validate(request.data)

        # Get reconciliation
        reconciliation = self._get_reconciliation(request_data.payment_reconciliation)

        # Authorize: user must have read permission
        authorize_payment_reconciliation_read(reconciliation, request.user)

        return Response(self._serialize_reconciliation_with_meta(reconciliation))

    @extend_schema(request=TransactionStatusSpec)
    @action(detail=False, methods=["POST"])
    def refresh_transaction_status(self, request):
        """
        Manually refresh transaction status from Pine Labs.

        Fetches the latest status from Plutus and updates the PaymentReconciliation
        record immediately, rather than waiting for background polling.

        Use this endpoint when you need real-time status updates.
        """
        request_data = TransactionStatusSpec.model_validate(request.data)
        reconciliation = self._get_reconciliation(request_data.payment_reconciliation)

        try:
            reconciliation, status_changed = refresh_payment_reconciliation_status(
                reconciliation,
                user=request.user,
            )
        except ValidationError as e:
            logger.error(
                "PaymentReconciliation %s missing pinelabs metadata for refresh",
                reconciliation.external_id,
            )
            return Response(
                {
                    "errors": [
                        {
                            "type": "pinelabs_metadata_missing",
                            "msg": str(e),
                        }
                    ]
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except PermissionDenied:
            raise
        except Exception as e:
            logger.error(
                "Pinelabs refresh_transaction_status API call failed: %s",
                str(e),
                exc_info=True,
            )
            return Response(
                {
                    "errors": [
                        {
                            "type": "pinelabs_api_error",
                            "msg": "Failed to fetch status from Pine Labs. Please try again later.",
                        }
                    ]
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        response_data = self._serialize_reconciliation_with_meta(reconciliation)
        response_data["status_changed"] = status_changed

        return Response(response_data)

    @extend_schema(request=CancelTransactionSpec)
    @action(detail=False, methods=["POST"])
    def cancel_transaction(self, request):
        request_data = CancelTransactionSpec.model_validate(request.data)
        reconciliation = self._get_reconciliation(request_data.payment_reconciliation)

        # Authorize FIRST before any external API calls
        authorize_payment_reconciliation_cancel(reconciliation, request.user)

        pinelabs_meta = (reconciliation.meta or {}).get(PINELABS_META_KEY, {})
        terminal_external_id = pinelabs_meta.get("terminal_id")
        transaction_reference_id = pinelabs_meta.get("transaction_reference_id")
        if not terminal_external_id or transaction_reference_id is None:
            return Response(
                {
                    "errors": [
                        {
                            "type": "pinelabs_metadata_missing",
                            "msg": "PaymentReconciliation has no pinelabs metadata",
                        }
                    ]
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        terminal = self._get_terminal(terminal_external_id)

        plutus_response = PlutusCloudService().cancel_transaction(
            CancelTransactionRequestData(
                plutus_transaction_reference_id=str(transaction_reference_id),
                merchant_id=terminal.config.pinelabs_merchant_id,
                security_token=terminal.config.pinelabs_security_token,
                client_id=terminal.device.metadata["client_id"],
                store_id=terminal.device.metadata["store_id"],
                amount=rupees_to_paise(reconciliation.amount),
            )
        )

        if plutus_response.response_code != PLUTUS_RESPONSE_CODE_APPROVED:
            logger.warning(
                "Pinelabs cancel_transaction failed: code=%s message=%s",
                plutus_response.response_code,
                plutus_response.response_message,
            )
            return Response(
                {
                    "errors": [
                        {
                            "type": "pinelabs_cancel_failed",
                            "msg": plutus_response.response_message,
                            "code": plutus_response.response_code,
                        }
                    ]
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        reconciliation = cancel_payment_reconciliation(
            reconciliation,
            user=request.user,
            status=PaymentReconciliationStatusOptions.cancelled,
            meta=build_cancel_meta(reconciliation.meta or {}, plutus_response),
        )

        return Response(self._serialize_reconciliation(reconciliation))
