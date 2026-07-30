from django.db import models

from care.emr.models.base import EMRBaseModel


class PinelabsPosTerminal(EMRBaseModel):
    config = models.ForeignKey("care_pinelabs.PinelabsConfig", on_delete=models.CASCADE)
    device = models.OneToOneField("emr.Device", on_delete=models.CASCADE)
