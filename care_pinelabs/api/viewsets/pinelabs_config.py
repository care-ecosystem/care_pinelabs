from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from care.emr.api.viewsets.base import EMRBaseViewSet, EMRRetrieveMixin
from care.emr.models.device import Device
from care.facility.models import Facility
from care.security.authorization import AuthorizationController
from care.utils.shortcuts import get_object_or_404
from care_pinelabs.api.specs.pinelabs_config import (
    PinelabsConfigCreateSpec,
    PinelabsConfigReadSpec,
)
from care_pinelabs.models.pinelabs_config import PinelabsConfig
from care_pinelabs.models.pinelabs_payment_method_mapping import (
    PinelabsPaymentMethodMapping,
)
from care_pinelabs.models.pinelabs_pos_terminal import PinelabsPosTerminal


@extend_schema(tags=["Pinelabs: Pinelabs Config"])
class PinelabsConfigViewSet(EMRRetrieveMixin, EMRBaseViewSet):
    database_model = PinelabsConfig
    pydantic_model = PinelabsConfigCreateSpec
    pydantic_read_model = PinelabsConfigReadSpec

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("facility", "created_by", "updated_by")
            .prefetch_related("payment_method_mappings", "pinelabspositerminal_set")
        )

    def _authorize_facility(self, facility):
        if not AuthorizationController.call(
            "can_manage_pinelabs_config", self.request.user, facility
        ):
            raise PermissionDenied(
                "You are not authorized to manage Pinelabs config for this facility"
            )

    def authorize_retrieve(self, instance):
        self._authorize_facility(instance.facility)

    @staticmethod
    def _conflict(msg: str) -> Response:
        return Response(
            {"errors": [{"type": "conflict", "msg": msg}]},
            status=status.HTTP_409_CONFLICT,
        )

    def _get_device(self, device_id) -> Device:
        device = get_object_or_404(Device, external_id=device_id)
        if device.care_type != "pos-terminal":
            raise ValidationError(f"Device {device_id} is not a pos-terminal")
        return device

    @extend_schema(request=PinelabsConfigCreateSpec, responses=PinelabsConfigReadSpec)
    def create(self, request, *args, **kwargs):
        request_data = PinelabsConfigCreateSpec(**request.data)
        facility = get_object_or_404(Facility, external_id=request_data.facility_id)
        self._authorize_facility(facility)

        if PinelabsConfig.objects.filter(facility=facility).exists():
            return self._conflict("Pinelabs config already exists for this facility")

        devices = []
        for pos_terminal in request_data.pos_terminals or []:
            device = self._get_device(pos_terminal.device_id)
            if PinelabsPosTerminal.objects.filter(device=device).exists():
                return self._conflict(
                    "This device is already linked to another Pinelabs pos terminal"
                )
            devices.append(device)

        with transaction.atomic():
            config = PinelabsConfig.objects.create(
                facility=facility,
                default_payment_flow=request_data.default_payment_flow,
                allow_advance_payment=request_data.allow_advance_payment,
                allow_partial_payment=request_data.allow_partial_payment,
                pinelabs_merchant_id=request_data.pinelabs_merchant_id,
                pinelabs_security_token=request_data.pinelabs_security_token,
                created_by=request.user,
                updated_by=request.user,
            )

            for mapping in request_data.payment_method_mappings or []:
                PinelabsPaymentMethodMapping.objects.create(
                    config=config,
                    care_method=mapping.care_method,
                    pinelabs_method=mapping.pinelabs_method,
                    is_default=mapping.is_default,
                )

            for device in devices:
                PinelabsPosTerminal.objects.create(
                    config=config,
                    device=device,
                    created_by=request.user,
                    updated_by=request.user,
                )

        config = self.get_queryset().get(pk=config.pk)
        return Response(
            PinelabsConfigReadSpec.serialize(config).to_json(),
            status=status.HTTP_201_CREATED,
        )
