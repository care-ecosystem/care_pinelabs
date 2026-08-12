from datetime import datetime

from pydantic import UUID4, field_validator

from care.emr.models.device import Device
from care.emr.resources.base import EMRResource
from care.emr.resources.payment_reconciliation.spec import (
    PaymentReconciliationPaymentMethodOptions as CarePaymentMethod,
)
from care_pinelabs.models.pinelabs_config import PaymentFlowChoices, PinelabsConfig
from care_pinelabs.models.pinelabs_payment_method_mapping import (
    PinelabsPaymentMethodMapping,
    PinelabsPaymentModeChoices,
)
from care_pinelabs.models.pinelabs_pos_terminal import PinelabsPosTerminal


def _validate_payment_method_mappings(mappings):
    if not mappings:
        return mappings
    if sum(1 for m in mappings if m.is_default) > 1:
        msg = "At most one payment_method_mapping may be marked is_default = true"
        raise ValueError(msg)
    methods = [m.pinelabs_method for m in mappings]
    if len(methods) != len(set(methods)):
        msg = "Duplicate pinelabs_method within the same config"
        raise ValueError(msg)
    ids = [m.id for m in mappings if m.id]
    if len(ids) != len(set(ids)):
        msg = "Duplicate payment_method_mapping id within the same config"
        raise ValueError(msg)
    return mappings


def _validate_pos_terminals(terminals):
    if not terminals:
        return terminals
    device_ids = [t.device_id for t in terminals]
    if len(device_ids) != len(set(device_ids)):
        msg = "Duplicate device_id within the same config"
        raise ValueError(msg)
    return terminals


# ===================== Payment Method Mapping (embedded) =====================
class PinelabsPaymentMethodMappingWriteSpec(EMRResource):
    __model__ = PinelabsPaymentMethodMapping
    __exclude__ = ["config"]

    id: UUID4 | None = None
    care_method: CarePaymentMethod
    pinelabs_method: PinelabsPaymentModeChoices
    is_default: bool = False


class PinelabsPaymentMethodMappingReadSpec(EMRResource):
    __model__ = PinelabsPaymentMethodMapping
    __exclude__ = ["config"]

    id: UUID4 | None = None
    care_method: CarePaymentMethod
    pinelabs_method: PinelabsPaymentModeChoices
    is_default: bool
    created_date: datetime
    modified_date: datetime


# ===================== POS Terminal (embedded) =====================
class PinelabsPosTerminalWriteSpec(EMRResource):
    __model__ = PinelabsPosTerminal
    __exclude__ = ["config", "device"]

    device_id: UUID4


class DeviceSummarySpec(EMRResource):
    __model__ = Device
    __exclude__ = ["facility", "managing_organization", "current_location", "current_encounter"]

    id: UUID4 | None = None
    registered_name: str | None = None
    care_type: str | None = None
    metadata: dict = {}


class PinelabsPosTerminalReadSpec(EMRResource):
    __model__ = PinelabsPosTerminal
    __exclude__ = ["config", "device"]

    id: UUID4 | None = None
    device: dict | None = None
    created_by: dict | None = None
    updated_by: dict | None = None
    created_date: datetime
    modified_date: datetime

    @classmethod
    def perform_extra_serialization(cls, mapping, obj):
        mapping["id"] = obj.external_id
        mapping["device"] = DeviceSummarySpec.serialize(obj.device).to_json()
        cls.serialize_audit_users(mapping, obj)


# ===================== Pinelabs Config =====================
class PinelabsConfigCreateSpec(EMRResource):
    __model__ = PinelabsConfig
    __exclude__ = ["facility"]

    facility_id: UUID4
    default_payment_flow: PaymentFlowChoices | None = None
    allow_advance_payment: bool = True
    allow_partial_payment: bool = False
    pinelabs_merchant_id: str
    pinelabs_security_token: str
    meta: dict = {}
    payment_method_mappings: list[PinelabsPaymentMethodMappingWriteSpec] | None = None

    @field_validator("payment_method_mappings")
    @classmethod
    def validate_payment_method_mappings(cls, mappings):
        return _validate_payment_method_mappings(mappings)


class PinelabsConfigUpdateSpec(EMRResource):
    __model__ = PinelabsConfig
    __exclude__ = ["facility"]

    default_payment_flow: PaymentFlowChoices | None = None
    allow_advance_payment: bool | None = None
    allow_partial_payment: bool | None = None
    pinelabs_merchant_id: str | None = None
    pinelabs_security_token: str | None = None
    meta: dict | None = None
    payment_method_mappings: list[PinelabsPaymentMethodMappingWriteSpec] | None = None

    @field_validator("payment_method_mappings")
    @classmethod
    def validate_payment_method_mappings(cls, mappings):
        return _validate_payment_method_mappings(mappings)


class PinelabsPosTerminalsUpdateSpec(EMRResource):
    __model__ = PinelabsPosTerminal
    __exclude__ = ["config", "device"]

    pos_terminals: list[PinelabsPosTerminalWriteSpec]

    @field_validator("pos_terminals")
    @classmethod
    def validate_pos_terminals(cls, terminals):
        return _validate_pos_terminals(terminals)


class PinelabsConfigReadSpec(EMRResource):
    __model__ = PinelabsConfig
    __exclude__ = ["facility", "pinelabs_security_token"]

    id: UUID4 | None = None
    facility_id: UUID4 | None = None
    default_payment_flow: PaymentFlowChoices | None = None
    allow_advance_payment: bool
    allow_partial_payment: bool
    pinelabs_merchant_id: str
    meta: dict | None = None
    payment_method_mappings: list[dict] = []
    created_by: dict | None = None
    updated_by: dict | None = None
    created_date: datetime
    modified_date: datetime

    @classmethod
    def perform_extra_serialization(cls, mapping, obj):
        mapping["id"] = obj.external_id
        mapping["facility_id"] = obj.facility.external_id
        mapping["payment_method_mappings"] = [
            PinelabsPaymentMethodMappingReadSpec.serialize(m).to_json()
            for m in obj.payment_method_mappings.all()
        ]
        mapping["meta"] = obj.meta or {}
        cls.serialize_audit_users(mapping, obj)

    def to_json(self):
        return self.model_dump(mode="json")
