import secrets

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import IntegrityError, models, transaction
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
    assets = models.ManyToManyField(Asset, null=True, blank=True, through="AssetCollectionAsset")
    url = models.CharField(max_length=255, unique=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    image = models.ImageField(
        max_length=FILENAME_MAX_LENGTH,
        blank=True,
        null=True,
        upload_to=collection_image_upload_path,
        validators=[FileExtensionValidator(allowed_extensions=VALID_THUMBNAIL_EXTENSIONS)],
    )
    visibility = models.CharField(max_length=255, default=PRIVATE, choices=ASSET_VISIBILITY_CHOICES, db_default=PRIVATE)

    def save(self, *args, **kwargs):
        if self._state.adding:
            # TODO(james): this, or something like it should be used wherever
            # we try to generate unique urls for things.
            while True:
                try:
                    self.url = secrets.token_urlsafe(8)
                    super().save(*args, **kwargs)
                except IntegrityError:
                    continue
                else:
                    break

    def __str__(self):
        return self.name


class AssetCollectionAsset(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE)
    collection = models.ForeignKey(AssetCollection, on_delete=models.CASCADE, related_name="collected_assets")
    create_time = models.DateTimeField(auto_now_add=True)
    order = models.PositiveIntegerField(default=0)

    @transaction.atomic
    def save(self, *args, **kwargs):
        other_assets = self.collection.collected_assets.all()
        print(other_assets)

    def __str__(self):
        return f"{self.order}: {self.asset.name}"

    class Meta:
        ordering = ("order",)
