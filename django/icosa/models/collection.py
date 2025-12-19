import secrets

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import IntegrityError, models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from icosa.models import Asset

from .common import (
    ASSET_VISIBILITY_CHOICES,
    FILENAME_MAX_LENGTH,
    PRIVATE,
    VALID_THUMBNAIL_EXTENSIONS,
)
from .helpers import collection_image_upload_path


class AssetCollection(models.Model):
    create_time = models.DateTimeField(_("Created"), auto_now_add=True)
    update_time = models.DateTimeField(_("Last Updated"), auto_now=True, null=True, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("User"),
        on_delete=models.CASCADE,
        related_name="user_collections",
        help_text=_("Owner of this collection"),
    )
    assets = models.ManyToManyField(
        Asset,
        verbose_name=_("Assets"),
        blank=True,
        through="AssetCollectionAsset",
        help_text=_("Assets included in this collection"),
    )
    url = models.CharField(_("URL"), max_length=255, unique=True, help_text=_("Unique URL identifier for this collection"))
    name = models.CharField(_("Name"), max_length=255, help_text=_("Collection name"))
    description = models.TextField(_("Description"), blank=True, null=True, help_text=_("Collection description"))
    image = models.ImageField(
        _("Image"),
        max_length=FILENAME_MAX_LENGTH,
        blank=True,
        null=True,
        upload_to=collection_image_upload_path,
        validators=[FileExtensionValidator(allowed_extensions=VALID_THUMBNAIL_EXTENSIONS)],
        help_text=_("Cover image for this collection"),
    )
    visibility = models.CharField(
        _("Visibility"),
        max_length=255,
        default=PRIVATE,
        choices=ASSET_VISIBILITY_CHOICES,
        db_default=PRIVATE,
        help_text=_("Who can view this collection"),
    )

    class Meta:
        verbose_name = _("Asset Collection")
        verbose_name_plural = _("Asset Collections")

    def get_thumbnail_url(self):
        thumbnail_url = (
            f"{settings.DEPLOYMENT_SCHEME}{settings.DEPLOYMENT_HOST_WEB}{settings.STATIC_URL}images/nothumbnail.png?v=1"
        )

        collected_asset = self.collected_assets.first()
        if collected_asset:
            thumbnail_url = collected_asset.asset.get_thumbnail_url()

        return thumbnail_url

    def save(self, *args, **kwargs):
        if self._state.adding or not self.url:
            # TODO(james): this, or something like it should be used wherever
            # we try to generate unique urls for things.
            while True:
                try:
                    self.url = secrets.token_urlsafe(8)
                    super().save(*args, **kwargs)
                except IntegrityError:
                    continue
                else:
                    return
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        owner = self.user.assetowner_set.first()
        if not owner:
            return None
        return reverse(
            "icosa:user_asset_collection_view",
            kwargs={
                "user_url": owner.url,
                "collection_url": self.url,
            },
        )

    def __str__(self):
        return self.name or ""


class AssetCollectionAsset(models.Model):
    asset = models.ForeignKey(Asset, verbose_name=_("Asset"), on_delete=models.CASCADE)
    collection = models.ForeignKey(
        AssetCollection,
        verbose_name=_("Collection"),
        on_delete=models.CASCADE,
        related_name="collected_assets",
    )
    create_time = models.DateTimeField(_("Created"), auto_now_add=True)
    order = models.PositiveIntegerField(_("Order"), default=0, help_text=_("Display order in collection"))

    def __str__(self):
        return f"{self.order}: {self.asset.name}"

    class Meta:
        verbose_name = _("Collection Asset")
        verbose_name_plural = _("Collection Assets")
        ordering = ("order",)
