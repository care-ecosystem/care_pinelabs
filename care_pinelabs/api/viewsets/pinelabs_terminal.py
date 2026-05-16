from django_filters import rest_framework as filters
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from care.facility.models import Facility
from care.utils.shortcuts import get_object_or_404
from care_pinelabs.api.exceptions import pinelabs_exception_handler
from care_pinelabs.api.permissions import IsSuperUserOrReadOnly
from care_pinelabs.api.specs.pinelabs_terminal import (
    PinelabsTerminalReadSpec,
    PinelabsTerminalUpdateSpec,
    PinelabsTerminalWriteSpec,
)
from care_pinelabs.models.pinelabs_terminal import PinelabsTerminal


class PinelabsTerminalFilter(filters.FilterSet):
    facility = filters.UUIDFilter(field_name="facility__external_id")
    ordering = filters.OrderingFilter(
        fields=(
            "created_date",
            "modified_date",
        )
    )

    class Meta:
        model = PinelabsTerminal
        fields = ["facility"]


@extend_schema(tags=["Pinelabs: Pinelabs Terminal"])
class PinelabsTerminalViewSet(GenericViewSet):
    permission_classes = (IsSuperUserOrReadOnly,)
    queryset = PinelabsTerminal.objects.select_related("facility").all()
    lookup_field = "external_id"
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = PinelabsTerminalFilter

    def get_exception_handler(self):
        return pinelabs_exception_handler

    @staticmethod
    def _serialize(instance: PinelabsTerminal) -> dict:
        return PinelabsTerminalReadSpec.from_instance(instance).model_dump(mode="json")

    def _get_facility(self, external_id) -> Facility:
        return get_object_or_404(Facility, external_id=external_id)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        paginator = self.paginator
        if paginator is not None:
            page = paginator.paginate_queryset(queryset, request, view=self)
            if page is not None:
                data = [self._serialize(instance) for instance in page]
                return paginator.get_paginated_response(data)
        return Response([self._serialize(instance) for instance in queryset])

    def retrieve(self, request, *args, **kwargs):
        return Response(self._serialize(self.get_object()))

    @extend_schema(request=PinelabsTerminalWriteSpec)
    def create(self, request, *args, **kwargs):
        request_data = PinelabsTerminalWriteSpec.model_validate(request.data)
        facility = self._get_facility(request_data.facility_id)
        instance = PinelabsTerminal.objects.create(
            facility=facility,
            name=request_data.name,
            client_id=request_data.client_id,
            store_id=request_data.store_id,
            is_active=request_data.is_active,
        )
        return Response(self._serialize(instance), status=status.HTTP_201_CREATED)

    @extend_schema(request=PinelabsTerminalUpdateSpec)
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        request_data = PinelabsTerminalUpdateSpec.model_validate(request.data)
        return Response(self._apply_update(instance, request_data))

    @extend_schema(request=PinelabsTerminalUpdateSpec)
    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def _apply_update(
        self,
        instance: PinelabsTerminal,
        request_data: PinelabsTerminalUpdateSpec,
    ) -> dict:
        update_fields = []
        if request_data.facility_id is not None:
            instance.facility = self._get_facility(request_data.facility_id)
            update_fields.append("facility")
        for field in ("name", "client_id", "store_id", "is_active"):
            value = getattr(request_data, field)
            if value is not None:
                setattr(instance, field, value)
                update_fields.append(field)
        if update_fields:
            instance.save(update_fields=update_fields)
        return self._serialize(instance)
