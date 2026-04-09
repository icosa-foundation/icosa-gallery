import logging
import secrets

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import IntegrityError, models
from django.urls import reverse
from django.utils import timezone
from icosa.model_mixins import (
    MOD_DEFERRED,
    MOD_MODIFIED,
    MOD_NEW,
    ModerationMixin,
)
from icosa.models import Asset

from .common import (
    ASSET_VISIBILITY_CHOICES,
    FILENAME_MAX_LENGTH,
    PRIVATE,
    VALID_THUMBNAIL_EXTENSIONS,
)
from .helpers import collection_image_upload_path

logger = logging.getLogger("django")


class AssetCollection(ModerationMixin):
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

    def get_displayname(self):
        # Used for compatibiliy with Asset and AssetCollection's methods of the
        # same name.
        return self.name

    def get_thumbnail_url(self):
        thumbnail_url = (
            f"{settings.DEPLOYMENT_SCHEME}{settings.DEPLOYMENT_HOST_WEB}{settings.STATIC_URL}images/nothumbnail.png?v=1"
        )

        collected_asset = self.collected_assets.first()
        if collected_asset:
            thumbnail_url = collected_asset.asset.get_thumbnail_url()

        return thumbnail_url

    @property
    def moderation_watch_fields(self):
        return [
            "url",
            "name",
            "description",
            "image",
        ]

    def save(self, *args, **kwargs):
        update_timestamps = kwargs.pop("update_timestamps", False)
        bypass_custom_logic = kwargs.pop("bypass_custom_logic", False)
        bypass_moderation_logging = kwargs.pop("bypass_moderation_logging", False)
        if self._state.adding and not self.url:
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
        if not bypass_custom_logic:
            now = timezone.now()
            if self._state.adding:
                self.create_time = now
            else:
                if update_timestamps:
                    self.update_time = now

        if not bypass_custom_logic and not bypass_moderation_logging:
            should_log = False
            try:
                changed_fields = []
                if self._state.adding:
                    changed_fields = self.moderation_watch_fields
                    moderation_state = MOD_NEW
                    should_log = True
                elif self.moderation_state != MOD_DEFERRED:
                    original_instance = AssetCollection.objects.get(pk=self.pk)
                    for field in self.moderation_watch_fields:
                        if getattr(self, field) != getattr(original_instance, field):
                            changed_fields.append(field)
                    moderation_state = MOD_MODIFIED
                    if changed_fields:
                        should_log = True
                else:
                    # Just for QA
                    moderation_state = self.moderation_state

                if should_log:
                    self.moderation_state = moderation_state
                    self.moderation_state_change_time = timezone.now()
                    self.moderation_state_change_by = None
                    if self.moderation_changed_fields:
                        self.moderation_changed_fields = list(set(self.moderation_changed_fields + changed_fields))
                    else:
                        self.moderation_changed_fields = changed_fields
            except Exception as e:
                logger.error(e)
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

    class Meta:
        indexes = [
            models.Index(fields=["moderation_state"]),
        ]


class AssetCollectionAsset(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE)
    collection = models.ForeignKey(AssetCollection, on_delete=models.CASCADE, related_name="collected_assets")
    create_time = models.DateTimeField(auto_now_add=True)
    order = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.order}: {self.asset.name}"

    class Meta:
        ordering = ("order",)
