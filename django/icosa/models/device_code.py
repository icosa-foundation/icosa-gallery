from django.conf import settings
from django.db import models


class DeviceCode(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    devicecode = models.CharField(max_length=6)
    expiry = models.DateTimeField()

    def __str__(self):
        return f"{self.devicecode}: {self.expiry}"
