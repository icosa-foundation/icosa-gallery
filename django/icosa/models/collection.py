import secrets

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import IntegrityError, models
from django.urls import reverse
from icosa.models import Asset

from .common import (
    ASSET_VISIBILITY_CHOICES,
    FILENAME_MAX_LENGTH,
    PRIVATE,
    VALID_THUMBNAIL_EXTENSIONS,
)
from .helpers import collection_image_upload_path


class AssetCollection(models.Model):
    create_time = models.DateTimeField(auto_now_add=True)
    update_time = models.DateTimeField(auto_now=True, null=True, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="user_collections")
    assets = models.ManyToManyField(Asset, blank=True, through="AssetCollectionAsset")
    url = models.CharField(max_length=255, unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    image = models.ImageField(
        max_length=FILENAME_MAX_LENGTH,
        blank=True,
        null=True,
        upload_to=collection_image_upload_path,
        validators=[FileExtensionValidator(allowed_extensions=VALID_THUMBNAIL_EXTENSIONS)],
    )
    visibility = models.CharField(max_length=255, default=PRIVATE, choices=ASSET_VISIBILITY_CHOICES, db_default=PRIVATE)

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
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE)
    collection = models.ForeignKey(AssetCollection, on_delete=models.CASCADE, related_name="collected_assets")
    create_time = models.DateTimeField(auto_now_add=True)
    order = models.PositiveIntegerField(default=0)

    # @transaction.atomic
    # def save(self, *args, **kwargs):
    #     other_assets = self.collection.collected_assets.all()
    #     print(other_assets)

    def __str__(self):
        return f"{self.order}: {self.asset.name}"

    class Meta:
        ordering = ("order",)
