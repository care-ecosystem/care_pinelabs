from enum import Enum

from pydantic import BaseModel


class AllowedPaymentMode(str, Enum):
    CARD = "1"
    PHONEPE = "8"
    UPI = "10"
    BHARAT_QR = "11"
    AMAZON_PAY = "21"


class MetaInfo(BaseModel):
    Tag: str
    Value: str | None


class UploadTransactionRequestData(BaseModel):
    transaction_number: str
    sequence_number: int = 1
    allowed_payment_mode: AllowedPaymentMode = AllowedPaymentMode.CARD
    amount: int
    user_id: str | None = None
    merchant_id: str
    security_token: str
    client_id: str
    store_id: str
    auto_cancel_duration_in_minutes: int = 5


class UploadTransactionResponseData(BaseModel):
    response_code: int
    response_message: str
    transaction_reference_id: int | None = None
    additional_info: list[MetaInfo] | None = None


class GetStatusRequestData(BaseModel):
    plutus_transaction_reference_id: str
    merchant_id: str
    security_token: str
    client_id: str
    store_id: str


class GetStatusResponseData(BaseModel):
    response_code: int
    response_message: str
    transaction_reference_id: int
    transaction_data: list[MetaInfo] | None = None


class CancelTransactionRequestData(BaseModel):
    plutus_transaction_reference_id: str
    merchant_id: str
    security_token: str
    client_id: str
    store_id: str
    amount: int


class CancelTransactionResponseData(BaseModel):
    response_code: int
    response_message: str
