from django.db import models

from care.emr.models.base import EMRBaseModel
from care_pinelabs.utils.encrypted_field import EncryptedCharField


class PinelabsConfig(EMRBaseModel):
    facility = models.OneToOneField("facility.Facility", on_delete=models.CASCADE)
    default_payment_flow = models.CharField(max_length=255, null=True, blank=True)
    enable_advance = models.BooleanField(default=True)
    enable_partial_payment = models.BooleanField(default=False)
    pinelabs_merchant_id = models.CharField(max_length=255, null=False, blank=False)
    pinelabs_security_token = EncryptedCharField(null=False, blank=False)
