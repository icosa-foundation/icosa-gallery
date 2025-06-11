from django.conf import settings
from django.db import models

from .asset import Asset


class UserLike(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="likedassets")
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE)
    date_liked = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        date_str = self.date_liked.strftime("%d/%m/%Y %H:%M:%S %Z")
        return f"{self.user.displayname} -> {self.asset.name} @ {date_str}"
