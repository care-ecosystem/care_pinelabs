from django.db import models

from care.utils.models.base import BaseModel


class PinelabsPosTerminal(BaseModel):
    config = models.ForeignKey("care_pinelabs.PinelabsConfig", on_delete=models.CASCADE)
    device = models.OneToOneField("emr.Device", on_delete=models.CASCADE)
