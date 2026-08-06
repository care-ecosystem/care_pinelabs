from django_filters import rest_framework as filters
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.filters import OrderingFilter

from care.emr.api.viewsets.base import EMRBaseViewSet, EMRListMixin
from care.facility.models.facility import Facility
from care.security.authorization.base import AuthorizationController
from care_pinelabs.api.specs.pinelabs_transaction import PinelabsTransactionReadSpec
from care_pinelabs.models.pinelabs_transaction import PinelabsTransaction


class PinelabsTransactionFilters(filters.FilterSet):
    status = filters.CharFilter(
        field_name="payment_reconciliation__outcome", lookup_expr="iexact"
    )
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
class PinelabsTransactionViewSet(EMRListMixin, EMRBaseViewSet):
    database_model = PinelabsTransaction
    pydantic_read_model = PinelabsTransactionReadSpec
    filterset_class = PinelabsTransactionFilters
    filter_backends = [filters.DjangoFilterBackend, OrderingFilter]
    ordering_fields = ["created_date", "modified_date"]

    def get_queryset(self):
        facility_id = self.request.query_params.get("facility_id")
        if not facility_id:
            raise ValidationError("facility_id is a required query parameter")
        facility = Facility.objects.filter(external_id=facility_id).first()
        if not facility or not AuthorizationController.call(
            "can_read_payment_reconciliation_in_facility", self.request.user, facility
        ):
            raise PermissionDenied("Cannot read payment reconciliation")

        return (
            super()
            .get_queryset()
            .filter(payment_reconciliation__isnull=False, terminal__config__facility=facility)
            .select_related(
                "terminal",
                "payment_reconciliation__location",
                "payment_reconciliation__target_invoice",
                "payment_reconciliation__account",
            )
        )
