import logging
from uuid import uuid4

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from care_pinelabs.api.serializers.gateway import (
    CancelTransactionSerializer,
    TransactionStatusSerializer,
    UploadTransactionSerializer,
)
from care_pinelabs.care_pinelabs.services.specs.plutus_cloud_uat import (
    CancelTransactionRequestData,
    GetStatusRequestData,
    UploadTransactionRequestData,
)
from care_pinelabs.services.plutus_cloud_uat import PlutusCloudUATService

logger = logging.getLogger(__name__)


@extend_schema(tags=["Pinelabs: Gateway"])
class GatewayViewSet(GenericViewSet):
    permission_classes = (IsAuthenticated,)

    serializer_action_classes = {
        "upload_transaction": UploadTransactionSerializer,
        "transaction_status": TransactionStatusSerializer,
        "cancel_transaction": CancelTransactionSerializer,
    }

    def get_serializer_class(self):
        if self.action in self.serializer_action_classes:
            return self.serializer_action_classes[self.action]

        return super().get_serializer_class()

    def validate_request(self, request):
        serializer = self.get_serializer(data=request.data)

        try:
            serializer.is_valid(raise_exception=True)
        except Exception as exception:
            warning_string = (
                f"Validation failed for request data: {request.data}, "
                f"Path: {request.path}, Method: {request.method}, "
                f"Error details: {exception!s}"
            )
            logger.info(warning_string)

            raise exception

        return serializer.validated_data

    @action(detail=False, methods=["POST"])
    def upload_transaction(self, request):
        validated_data = self.validate_request(request)

        request_data = UploadTransactionRequestData(
            transaction_number=str(uuid4()),
            sequence_number=1,
            allowed_payment_mode=validated_data["payment_mode"],
            amount=validated_data["amount"],
            user_id=None,
            client_id=validated_data["terminal"].client_id,
            store_id=validated_data["terminal"].store_id,
        )
        response = PlutusCloudUATService().upload_transaction(request_data)

        return Response(
            status=status.HTTP_200_OK,
            data=response.model_dump(),
        )

    @action(detail=False, methods=["POST"])
    def transaction_status(self, request):
        validated_data = self.validate_request(request)

        request_data = GetStatusRequestData(
            plutus_transaction_reference_id=validated_data["transaction_reference_id"],
            client_id=validated_data["terminal"].client_id,
            store_id=validated_data["terminal"].store_id,
        )
        response = PlutusCloudUATService().get_status(request_data)

        # TODO: create payment reconciliation here

        return Response(
            status=status.HTTP_200_OK,
            data=response.model_dump(),
        )

    @action(detail=False, methods=["POST"])
    def cancel_transaction(self, request):
        validated_data = self.validate_request(request)

        request_data = CancelTransactionRequestData(
            plutus_transaction_reference_id=validated_data["transaction_reference_id"],
            client_id=validated_data["terminal"].client_id,
            store_id=validated_data["terminal"].store_id,
            amount=validated_data["amount"],
        )
        response = PlutusCloudUATService().cancel_transaction(request_data)

        return Response(
            status=status.HTTP_200_OK,
            data=response.model_dump(),
        )
