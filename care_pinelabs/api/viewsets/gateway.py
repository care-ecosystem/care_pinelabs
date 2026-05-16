import logging
from uuid import uuid4

from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from care.emr.models.payment_reconciliation import PaymentReconciliation
from care.emr.resources.payment_reconciliation.spec import (
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
from care_pinelabs.models.pinelabs_terminal import PinelabsTerminal
from care_pinelabs.services.payment_reconciliation import (
    PINELABS_META_KEY,
    PLUTUS_RESPONSE_CODE_APPROVED,
    build_cancel_meta,
    build_upload_meta,
    cancel_payment_reconciliation,
    create_payment_reconciliation,
    rupees_to_paise,
)
from care_pinelabs.services.plutus_cloud import PlutusCloudService
from care_pinelabs.services.specs.plutus_cloud import (
    CancelTransactionRequestData,
    UploadTransactionRequestData,
)
from care_pinelabs.settings import plugin_settings
from care_pinelabs.tasks.poll_transaction_status import poll_pinelabs_transaction_status

logger = logging.getLogger(__name__)


@extend_schema(tags=["Pinelabs: Gateway"])
class GatewayViewSet(GenericViewSet):
    permission_classes = (IsAuthenticated,)

    def get_exception_handler(self):
        return pinelabs_exception_handler

    def _get_terminal(self, external_id) -> PinelabsTerminal:
        return get_object_or_404(PinelabsTerminal, external_id=external_id)

    def _get_reconciliation(self, external_id) -> PaymentReconciliation:
        return get_object_or_404(PaymentReconciliation, external_id=external_id)

    @staticmethod
    def _serialize_reconciliation(instance: PaymentReconciliation) -> dict:
        return PaymentReconciliationReadSpec.serialize(instance).to_json()

    @extend_schema(request=UploadTransactionSpec)
    @action(detail=False, methods=["POST"])
    def upload_transaction(self, request):
        request_data = UploadTransactionSpec.model_validate(request.data)
        terminal = self._get_terminal(request_data.terminal)
        user = request.user

        transaction_number = str(uuid4())
        plutus_response = PlutusCloudService().upload_transaction(
            UploadTransactionRequestData(
                transaction_number=transaction_number,
                sequence_number=1,
                allowed_payment_mode=request_data.payment_mode,
                amount=rupees_to_paise(request_data.amount),
                user_id=user.username,
                client_id=terminal.client_id,
                store_id=terminal.store_id,
                auto_cancel_duration_in_minutes=plugin_settings.PINELABS_AUTO_CANCEL_DURATION_MINUTES,
            )
        )

        if (
            plutus_response.response_code != PLUTUS_RESPONSE_CODE_APPROVED
            or plutus_response.transaction_reference_id is None
        ):
            logger.warning(
                "Pinelabs upload_transaction failed: code=%s message=%s",
                plutus_response.response_code,
                plutus_response.response_message,
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

        reconciliation = create_payment_reconciliation(
            request_data,
            facility=terminal.facility,
            user=user,
            meta=build_upload_meta(
                terminal=terminal,
                transaction_number=transaction_number,
                payment_mode=request_data.payment_mode.value,
                response=plutus_response,
            ),
        )
        transaction.on_commit(
            lambda: poll_pinelabs_transaction_status.delay(
                payment_reconciliation_id=reconciliation.id
            )
        )

        return Response(
            self._serialize_reconciliation(reconciliation),
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(request=TransactionStatusSpec)
    @action(detail=False, methods=["POST"])
    def transaction_status(self, request):
        request_data = TransactionStatusSpec.model_validate(request.data)
        reconciliation = self._get_reconciliation(request_data.payment_reconciliation)

        return Response(self._serialize_reconciliation(reconciliation))

    @extend_schema(request=CancelTransactionSpec)
    @action(detail=False, methods=["POST"])
    def cancel_transaction(self, request):
        request_data = CancelTransactionSpec.model_validate(request.data)
        reconciliation = self._get_reconciliation(request_data.payment_reconciliation)

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
                client_id=terminal.client_id,
                store_id=terminal.store_id,
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
