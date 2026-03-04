from django_filters import rest_framework as filters
from drf_spectacular.utils import extend_schema
from rest_framework.mixins import (
    CreateModelMixin,
    DestroyModelMixin,
    ListModelMixin,
    RetrieveModelMixin,
    UpdateModelMixin,
)
from rest_framework.viewsets import GenericViewSet

from care_pinelabs.api.permissions import IsSuperUserOrReadOnly
from care_pinelabs.api.serializers.pinelabs_terminal import PinelabsTerminalSerializer
from care_pinelabs.models.pinelabs_terminal import PinelabsTerminal


class PinelabsTerminalFilter(filters.FilterSet):
    facility = filters.UUIDFilter(field_name="facility__external_id")
    ordering = filters.OrderingFilter(
        fields=(
            "created_date",
            "updated_date",
        )
    )

    class Meta:
        model = PinelabsTerminal
        fields = ["facility"]


@extend_schema(tags=["Pinelabs: Pinelabs Terminal"])
class PinelabsTerminalViewSet(
    GenericViewSet,
    ListModelMixin,
    CreateModelMixin,
    RetrieveModelMixin,
    UpdateModelMixin,
    DestroyModelMixin,
):
    permission_classes = (IsSuperUserOrReadOnly,)
    queryset = PinelabsTerminal.objects.all()
    serializer_class = PinelabsTerminalSerializer
    lookup_field = "external_id"
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = PinelabsTerminalFilter
