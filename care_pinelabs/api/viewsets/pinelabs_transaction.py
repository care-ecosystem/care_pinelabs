from django_filters import rest_framework as filters
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.filters import OrderingFilter
from rest_framework.mixins import ListModelMixin
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from care.facility.models.facility import Facility
from care.security.authorization.base import AuthorizationController
from care.utils.shortcuts import get_object_or_404
from care_pinelabs.api.specs.pinelabs_transaction import PinelabsTransactionReadSpec
from care_pinelabs.models.terminal_transaction import PinelabsTerminalTransaction


class PinelabsTransactionFilters(filters.FilterSet):
    status = filters.CharFilter(field_name="status", lookup_expr="iexact")
    method = filters.CharFilter(field_name="payment_mode")
    location = filters.UUIDFilter(
        field_name="payment_reconciliation__location__external_id"
    )
    created_by = filters.UUIDFilter(
        field_name="payment_reconciliation__created_by__external_id"
    )
    created_date = filters.DateTimeFromToRangeFilter(field_name="created_date")
    terminal = filters.UUIDFilter(field_name="terminal__external_id")
    transaction_number = filters.CharFilter(field_name="transaction_number")


@extend_schema(tags=["Pinelabs: Pinelabs Transaction"])
class PinelabsTransactionViewSet(ListModelMixin, GenericViewSet):
    queryset = PinelabsTerminalTransaction.objects.filter(
        payment_reconciliation__isnull=False
    ).select_related("terminal", "payment_reconciliation__location")
    filterset_class = PinelabsTransactionFilters
    filter_backends = [filters.DjangoFilterBackend, OrderingFilter]
    ordering_fields = ["created_date", "modified_date"]

    @extend_schema(responses=PinelabsTransactionReadSpec)
    def list(self, request, *args, **kwargs):
        facility_id = request.query_params.get("facility_id")
        if not facility_id:
            raise ValidationError("facility_id is a required query parameter")
        facility = get_object_or_404(Facility, external_id=facility_id)
        if not AuthorizationController.call(
            "can_read_payment_reconciliation_in_facility", request.user, facility
        ):
            raise PermissionDenied("Cannot read payment reconciliation")

        queryset = self.filter_queryset(
            self.get_queryset().filter(terminal__config__facility=facility)
        )

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request)
        target_queryset = page if page is not None else queryset
        data = [
            PinelabsTransactionReadSpec.serialize(tt).to_json()
            for tt in target_queryset
        ]
        if page is not None:
            return paginator.get_paginated_response(data)
        return Response(data)
