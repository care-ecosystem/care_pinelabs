import json

from django.http.response import Http404
from pydantic import ValidationError as PydanticValidationError
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


def pinelabs_exception_handler(exc, context):
    """
    Unified exception handler for the pinelabs API.

    Translates pydantic validation errors and DRF/Django 404s into the
    ``{"errors": [{"type": ..., "msg": ...}]}`` envelope used across the
    CARE EMR APIs, falling back to DRF's default handler for everything else.
    """
    if isinstance(exc, PydanticValidationError):
        return Response({"errors": json.loads(exc.json())}, status=400)
    if isinstance(exc, Http404):
        return Response(
            {
                "errors": [
                    {
                        "type": "object_not_found",
                        "msg": exc.args[0] if exc.args else "Object not found",
                    }
                ]
            },
            status=404,
        )
    if isinstance(exc, DRFValidationError) and getattr(exc, "detail", None):
        detail = exc.detail
        if isinstance(detail, dict) and "errors" in detail:
            return Response(detail, status=400)
        if isinstance(detail, list):
            msg = " , ".join(str(item) for item in detail)
            return Response(
                {"errors": [{"type": "validation_error", "msg": msg}]}, status=400
            )
        return Response(
            {"errors": [{"type": "validation_error", "msg": detail}]}, status=400
        )
    return drf_exception_handler(exc, context)
