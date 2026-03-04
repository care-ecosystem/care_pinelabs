from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet


@extend_schema(tags=["Pinelabs: Health Check"])
class HealthCheckViewSet(ViewSet):
    @action(detail=False, methods=["GET"])
    def ping(self, request):
        return Response({"status": "ok"})
