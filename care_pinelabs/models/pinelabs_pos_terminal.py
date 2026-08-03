from django.db import models

from care.emr.models.base import EMRBaseModel


class PinelabsPosTerminal(EMRBaseModel):
    config = models.ForeignKey("care_pinelabs.PinelabsConfig", on_delete=models.CASCADE)
    device = models.ForeignKey("emr.Device", on_delete=models.CASCADE)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["device"],
                condition=models.Q(deleted=False),
                name="unique_active_device_per_pos_terminal",
            ),
        ]
