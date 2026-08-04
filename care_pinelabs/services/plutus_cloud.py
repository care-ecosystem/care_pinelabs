import requests

from care_pinelabs.services.specs.plutus_cloud import (
    CancelTransactionRequestData,
    CancelTransactionResponseData,
    GetStatusRequestData,
    GetStatusResponseData,
    UploadTransactionRequestData,
    UploadTransactionResponseData,
)
from care_pinelabs.settings import plugin_settings


class PlutusCloudService:
    def __init__(self):
        self.base_endpoint = (
            plugin_settings.PINELABS_API_BASE_URL + "/api/CloudBasedIntegration/V1"
        )

    def upload_transaction(
        self, data: UploadTransactionRequestData
    ) -> UploadTransactionResponseData:
        url = f"{self.base_endpoint}/UploadBilledTransaction"
        payload = {
            "TransactionNumber": data.transaction_number,
            "SequenceNumber": data.sequence_number,
            "AllowedPaymentMode": data.allowed_payment_mode.value,
            "Amount": data.amount,
            "UserID": data.user_id or "",
            "MerchantID": data.merchant_id,
            "SecurityToken": data.security_token,
            "Clientid": data.client_id,
            "Storeid": data.store_id,
            "AutoCancelDurationInMinutes": data.auto_cancel_duration_in_minutes,
        }
        response = requests.post(
            url, json=payload, timeout=plugin_settings.PINELABS_API_TIMEOUT
        )
        response.raise_for_status()  # Raise HTTPError for 4xx/5xx responses

        response_data = response.json()
        return UploadTransactionResponseData(
            response_code=response_data.get("ResponseCode", -1),
            response_message=response_data.get("ResponseMessage", "Unknown Error"),
            transaction_reference_id=response_data.get(
                "PlutusTransactionReferenceID", None
            ),
            additional_info=response_data.get("AdditionalInfo", None),
        )

    def get_status(self, data: GetStatusRequestData) -> GetStatusResponseData:
        url = f"{self.base_endpoint}/GetCloudBasedTxnStatus"
        payload = {
            "MerchantID": data.merchant_id,
            "SecurityToken": data.security_token,
            "Clientid": data.client_id,
            "Storeid": data.store_id,
            "PlutusTransactionReferenceID": data.plutus_transaction_reference_id,
        }

        response = requests.post(
            url, json=payload, timeout=plugin_settings.PINELABS_API_TIMEOUT
        )
        response.raise_for_status()  # Raise HTTPError for 4xx/5xx responses

        response_data = response.json()
        return GetStatusResponseData(
            response_code=response_data.get("ResponseCode", -1),
            response_message=response_data.get("ResponseMessage", "Unknown Error"),
            transaction_reference_id=response_data.get(
                "PlutusTransactionReferenceID", -1
            ),
            transaction_data=response_data.get("TransactionData", None),
        )

    def cancel_transaction(
        self, data: CancelTransactionRequestData
    ) -> CancelTransactionResponseData:
        url = f"{self.base_endpoint}/CancelTransactionForced"
        payload = {
            "MerchantID": data.merchant_id,
            "SecurityToken": data.security_token,
            "Clientid": data.client_id,
            "Storeid": data.store_id,
            "PlutusTransactionReferenceID": data.plutus_transaction_reference_id,
            "Amount": data.amount,
            "TakeToHomeScreen": True,
            "ConfirmationRequired": False,
        }

        response = requests.post(
            url, json=payload, timeout=plugin_settings.PINELABS_API_TIMEOUT
        )
        response.raise_for_status()  # Raise HTTPError for 4xx/5xx responses

        response_data = response.json()
        return CancelTransactionResponseData(
            response_code=response_data.get("ResponseCode", -1),
            response_message=response_data.get("ResponseMessage", "Unknown Error"),
        )
