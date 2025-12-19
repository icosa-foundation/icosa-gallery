from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser
from django.db import models
from django.db.models import QuerySet
from django.urls import reverse
from django.utils.translation import gettext_lazy as _


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
    url = models.CharField(
        _("User Name / URL"),
        max_length=255,
        unique=True,
        help_text=_("Unique username or URL identifier for this creator"),
    )
    email = models.EmailField(_("Email"), max_length=255, null=True, blank=True, help_text=_("Creator's email address"))
    displayname = models.CharField(
        _("Display Name"),
        max_length=255,
        blank=False,
        default=None,
        help_text=_("Public display name shown to users"),
    )
    description = models.TextField(_("Description"), blank=True, null=True, help_text=_("Creator profile description"))
    migrated = models.BooleanField(_("Migrated"), default=False, help_text=_("Whether this account was migrated from another system"))
    imported = models.BooleanField(_("Imported"), default=False, help_text=_("Whether this account was imported from Google Poly"))
    is_claimed = models.BooleanField(_("Is Claimed"), default=True, help_text=_("Whether this account has been claimed by a user"))
    django_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("Django User"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text=_("Associated Django user account"),
    )
    merged_with = models.ForeignKey(
        "self",
        verbose_name=_("Merged With"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text=_("Another asset owner this account was merged with"),
        related_name="merged_owners",
    )
    disable_profile = models.BooleanField(_("Disable Profile"), default=False, help_text=_("Whether the profile page is disabled"))

    objects = AssetOwnerManager()

    class Meta:
        verbose_name = _("Asset Owner")
        verbose_name_plural = _("Asset Owners")

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
