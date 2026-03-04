from django.db import models

from care.utils.models.base import BaseModel


class PinelabsTerminal(BaseModel):
    facility = models.ForeignKey("facility.Facility", on_delete=models.CASCADE)
    client_id = models.CharField(max_length=255, null=False, blank=False)
    store_id = models.CharField(max_length=255, null=False, blank=False)
    name = models.CharField(max_length=255, null=False, blank=False)
    is_active = models.BooleanField(default=True)
