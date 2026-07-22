from django.db import models

from care.utils.models.base import BaseModel


class PinelabsConfig(BaseModel):
    facility = models.OneToOneField("facility.Facility", on_delete=models.CASCADE)
    default_payment_flow = models.CharField(max_length=255, null=True, blank=True)
    payment_methods = models.JSONField(default=list)
    enable_advance = models.BooleanField(default=True)
    enable_partial_payment = models.BooleanField(default=False)
    pinelabs_merchant_id = models.CharField(max_length=255, null=False, blank=False)
    pinelabs_security_token = models.CharField(max_length=255, null=False, blank=False)
