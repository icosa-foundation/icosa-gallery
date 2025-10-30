from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser
from django.db import models
from django.db.models import QuerySet
from django.urls import reverse


class AssetOwnerManager(models.Manager):
    def get_unclaimed_for_user(self, user: AbstractBaseUser) -> QuerySet:
        """Get the list of unclaimed asset owners for a user.

        Args:
            user (User): The user to get unclaimed asset owners for.

        Returns:
            List[Self]: A list of unclaimed asset owners.
        """
        return self.filter(
            django_user=None,
            is_claimed=False,
            email=user.email,
            url=user.username,
        )


class AssetOwner(models.Model):
    id = models.BigAutoField(primary_key=True)
    url = models.CharField("User Name / URL", max_length=255, unique=True)
    email = models.EmailField(max_length=255, null=True, blank=True)
    displayname = models.CharField("Display Name", max_length=255, blank=False, default=None)
    description = models.TextField(blank=True, null=True)
    migrated = models.BooleanField(default=False)
    imported = models.BooleanField(default=False)
    is_claimed = models.BooleanField(default=True)
    django_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    merged_with = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    disable_profile = models.BooleanField(default=False)

    objects = AssetOwnerManager()

    def get_displayname(self):
        if self.django_user:
            result = self.django_user.displayname or self.displayname
        else:
            result = self.displayname
        return result

    def get_absolute_url(self):
        if self.url:
            return reverse("icosa:user_show", kwargs={"slug": self.url})
        else:
            return ""

    def __str__(self):
        return self.displayname
