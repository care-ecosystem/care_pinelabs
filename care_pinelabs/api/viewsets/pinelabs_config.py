from django.db import IntegrityError, transaction
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from care.emr.api.viewsets.base import EMRBaseViewSet, EMRRetrieveMixin
from care.emr.models.device import Device
from care.emr.models.organization import FacilityOrganization, FacilityOrganizationUser
from care.facility.models import Facility
from care.security.authorization import AuthorizationController
from care.utils.shortcuts import get_object_or_404
from care_pinelabs.api.specs.pinelabs_config import (
    PinelabsConfigCreateSpec,
    PinelabsConfigReadSpec,
    PinelabsConfigUpdateSpec,
    PinelabsPosTerminalReadSpec,
    PinelabsPosTerminalsUpdateSpec,
)
from care_pinelabs.models.pinelabs_config import PinelabsConfig
from care_pinelabs.models.pinelabs_payment_method_mapping import (
    PinelabsPaymentMethodMapping,
)
from care_pinelabs.models.pinelabs_pos_terminal import PinelabsPosTerminal


class _ConflictError(Exception):
    pass


PinelabsPosTerminalReadSpecList = list[PinelabsPosTerminalReadSpec]


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
            .prefetch_related("payment_method_mappings")
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

    @extend_schema(responses=PinelabsConfigReadSpec)
    def list(self, request, *args, **kwargs):
        facility_id = request.query_params.get("facility_id")
        if not facility_id:
            raise ValidationError("facility_id is a required query parameter")
        facility = get_object_or_404(Facility, external_id=facility_id)
        self._authorize_facility(facility)
        instance = get_object_or_404(self.get_queryset(), facility=facility)
        return Response(PinelabsConfigReadSpec.serialize(instance).to_json())

    @staticmethod
    def _conflict(msg: str) -> Response:
        return Response(
            {"errors": [{"type": "conflict", "msg": msg}]},
            status=status.HTTP_409_CONFLICT,
        )

    def _get_device(self, device_id, facility) -> Device:
        device = get_object_or_404(Device, external_id=device_id)
        if device.care_type != "pos-terminal":
            raise ValidationError(f"Device {device_id} is not a pos-terminal")
        if device.facility_id != facility.id:
            raise ValidationError(f"Device {device_id} does not belong to this facility")
        return device

    @extend_schema(request=PinelabsConfigCreateSpec, responses=PinelabsConfigReadSpec)
    def create(self, request, *args, **kwargs):
        request_data = PinelabsConfigCreateSpec(**request.data)
        facility = get_object_or_404(Facility, external_id=request_data.facility_id)
        self._authorize_facility(facility)

        try:
            with transaction.atomic():
                existing_config = PinelabsConfig._base_manager.filter(
                    facility=facility
                ).first()
                if existing_config and not existing_config.deleted:
                    raise _ConflictError(
                        "Pinelabs config already exists for this facility"
                    )

                config = existing_config or PinelabsConfig(facility=facility)
                config.deleted = False
                config.default_payment_flow = request_data.default_payment_flow
                config.allow_advance_payment = request_data.allow_advance_payment
                config.allow_partial_payment = request_data.allow_partial_payment
                config.pinelabs_merchant_id = request_data.pinelabs_merchant_id
                config.pinelabs_security_token = request_data.pinelabs_security_token
                config.created_by = request.user
                config.updated_by = request.user
                try:
                    config.save()
                except IntegrityError:
                    raise _ConflictError(
                        "Pinelabs config already exists for this facility"
                    ) from None

                self._replace_payment_method_mappings(
                    config, request_data.payment_method_mappings or []
                )
        except _ConflictError as e:
            return self._conflict(str(e))

        config = self.get_queryset().get(pk=config.pk)
        return Response(
            PinelabsConfigReadSpec.serialize(config).to_json(),
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(request=PinelabsConfigUpdateSpec, responses=PinelabsConfigReadSpec)
    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        self._authorize_facility(instance.facility)
        request_data = PinelabsConfigUpdateSpec(**request.data)

        try:
            with transaction.atomic():
                update_fields = []
                for field in (
                    "default_payment_flow",
                    "allow_advance_payment",
                    "allow_partial_payment",
                    "pinelabs_merchant_id",
                    "pinelabs_security_token",
                ):
                    value = getattr(request_data, field)
                    if value is not None:
                        setattr(instance, field, value)
                        update_fields.append(field)
                touched = bool(update_fields)

                if request_data.payment_method_mappings is not None:
                    self._replace_payment_method_mappings(
                        instance, request_data.payment_method_mappings
                    )
                    touched = True

                if touched:
                    instance.updated_by = request.user
                    instance.save(
                        update_fields=[*update_fields, "updated_by", "modified_date"]
                    )
        except _ConflictError as e:
            return self._conflict(str(e))
        except IntegrityError:
            return self._conflict(
                "A conflicting payment method mapping already exists for this config"
            )

        instance = self.get_queryset().get(pk=instance.pk)
        return Response(PinelabsConfigReadSpec.serialize(instance).to_json())

    @extend_schema(responses=PinelabsPosTerminalReadSpecList)
    @action(detail=True, methods=["get"], url_path="pos-terminals")
    def pos_terminals(self, request, *args, **kwargs):
        instance = self.get_object()
        self._authorize_facility(instance.facility)
        terminals = PinelabsPosTerminal.objects.filter(config=instance).select_related(
            "device", "created_by", "updated_by"
        )

        if request.query_params.get("mine", "false").lower() == "true":
            facility_organizations = FacilityOrganization.objects.filter(
                facility=instance.facility
            ).values_list("id", flat=True)
            if request.user.is_superuser:
                users_facility_organizations = facility_organizations
            else:
                users_facility_organizations = FacilityOrganizationUser.objects.filter(
                    organization_id__in=facility_organizations, user=request.user
                ).values_list("organization_id", flat=True)
            terminals = terminals.filter(
                device__facility_organization_cache__overlap=list(
                    users_facility_organizations
                )
            )

        return Response(
            [PinelabsPosTerminalReadSpec.serialize(t).to_json() for t in terminals]
        )

    @extend_schema(
        request=PinelabsPosTerminalsUpdateSpec, responses=PinelabsPosTerminalReadSpecList
    )
    @pos_terminals.mapping.patch
    def _update_pos_terminals(self, request, *args, **kwargs):
        instance = self.get_object()
        self._authorize_facility(instance.facility)
        request_data = PinelabsPosTerminalsUpdateSpec(**request.data)

        try:
            with transaction.atomic():
                instance = PinelabsConfig.objects.select_for_update().get(
                    pk=instance.pk
                )

                linked_device_ids = set(
                    PinelabsPosTerminal.objects.filter(config=instance).values_list(
                        "device__external_id", flat=True
                    )
                )
                new_devices_by_id = {}
                for pos_terminal in request_data.pos_terminals:
                    if pos_terminal.device_id in linked_device_ids:
                        continue
                    device = self._get_device(pos_terminal.device_id, instance.facility)
                    if (
                        PinelabsPosTerminal.objects.filter(device=device)
                        .exclude(config=instance)
                        .exists()
                    ):
                        raise _ConflictError(
                            f"Device {device.registered_name} is already linked "
                            "to another Pinelabs POS terminal"
                        )
                    new_devices_by_id[pos_terminal.device_id] = device

                self._replace_pos_terminals(
                    instance, request_data.pos_terminals, new_devices_by_id, request.user
                )
                instance.updated_by = request.user
                instance.save(update_fields=["updated_by", "modified_date"])
        except _ConflictError as e:
            return self._conflict(str(e))
        except IntegrityError:
            return self._conflict(
                "This device is already linked to another Pinelabs POS terminal"
            )

        terminals = PinelabsPosTerminal.objects.filter(config=instance).select_related(
            "device", "created_by", "updated_by"
        )
        return Response(
            [PinelabsPosTerminalReadSpec.serialize(t).to_json() for t in terminals]
        )

    @staticmethod
    def _replace_payment_method_mappings(config, mappings_spec):
        existing_by_id = {
            m.external_id: m
            for m in PinelabsPaymentMethodMapping._base_manager.filter(config=config)
        }
        for mapping in existing_by_id.values():
            if not mapping.deleted:
                mapping.deleted = True
                mapping.save(update_fields=["deleted"])

        referenced_ids = {spec.id for spec in mappings_spec if spec.id}
        existing_by_method = {}
        for external_id, mapping in existing_by_id.items():
            if external_id not in referenced_ids:
                existing_by_method.setdefault(mapping.pinelabs_method, mapping)

        for spec in mappings_spec:
            if spec.id:
                mapping = existing_by_id.get(spec.id)
                if mapping is None:
                    raise ValidationError(f"payment_method_mapping {spec.id} not found")
            else:
                mapping = existing_by_method.pop(spec.pinelabs_method, None)

            if mapping:
                mapping.care_method = spec.care_method
                mapping.pinelabs_method = spec.pinelabs_method
                mapping.is_default = spec.is_default
                mapping.deleted = False
                mapping.save()
            else:
                PinelabsPaymentMethodMapping.objects.create(
                    config=config,
                    care_method=spec.care_method,
                    pinelabs_method=spec.pinelabs_method,
                    is_default=spec.is_default,
                )

    @staticmethod
    def _replace_pos_terminals(config, terminals_spec, new_devices_by_id, user):
        existing_by_device_id = {
            terminal.device.external_id: terminal
            for terminal in PinelabsPosTerminal._base_manager.select_related(
                "device"
            ).filter(config=config)
        }
        submitted_device_ids = {spec.device_id for spec in terminals_spec}

        for device_external_id, terminal in existing_by_device_id.items():
            if not terminal.deleted and device_external_id not in submitted_device_ids:
                terminal.deleted = True
                terminal.updated_by = user
                terminal.save(update_fields=["deleted", "updated_by"])

        for spec in terminals_spec:
            existing = existing_by_device_id.get(spec.device_id)
            if existing:
                if existing.deleted:
                    existing.deleted = False
                    existing.updated_by = user
                    existing.save(update_fields=["deleted", "updated_by"])
                continue

            device = new_devices_by_id[spec.device_id]
            other_terminal = (
                PinelabsPosTerminal._base_manager.select_for_update()
                .filter(device=device)
                .first()
            )
            if other_terminal:
                if not other_terminal.deleted:
                    raise _ConflictError(
                        f"Device {device.registered_name} is already linked "
                        "to another Pinelabs POS terminal"
                    )
                other_terminal.config = config
                other_terminal.deleted = False
                other_terminal.updated_by = user
                other_terminal.save(update_fields=["config", "deleted", "updated_by"])
            else:
                PinelabsPosTerminal.objects.create(
                    config=config,
                    device=device,
                    created_by=user,
                    updated_by=user,
                )
