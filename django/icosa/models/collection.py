import logging
import secrets

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone

from icosa.model_mixins import (
    MOD_DEFERRED,
    MOD_HIDDEN,
    MOD_MODIFIED,
    MOD_NEW,
    ModerationMixin,
)
from icosa.models import Asset

from .common import (
    ASSET_VISIBILITY_CHOICES,
    FILENAME_MAX_LENGTH,
    PRIVATE,
    PUBLIC,
    VALID_THUMBNAIL_EXTENSIONS,
)
from .helpers import collection_image_upload_path

logger = logging.getLogger("django")


class AssetCollection(ModerationMixin):
    create_time = models.DateTimeField(auto_now_add=True)
    update_time = models.DateTimeField(auto_now=True, null=True, blank=True)
    owner = models.ForeignKey(
        "AssetOwner",
        on_delete=models.CASCADE,
        related_name="asset_collections",
    )
    assets = models.ManyToManyField(Asset, blank=True, through="AssetCollectionAsset")
    url = models.CharField(max_length=255, unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    markdown = models.BooleanField(
        default=False,
        help_text="Render the collection description as Markdown.",
    )
    image = models.ImageField(
        max_length=FILENAME_MAX_LENGTH,
        blank=True,
        null=True,
        upload_to=collection_image_upload_path,
        validators=[FileExtensionValidator(allowed_extensions=VALID_THUMBNAIL_EXTENSIONS)],
    )
    visibility = models.CharField(max_length=255, default=PRIVATE, choices=ASSET_VISIBILITY_CHOICES, db_default=PRIVATE)
    query_parameters = models.JSONField(blank=True, null=True, default=None)

    @property
    def is_dynamic(self):
        return self.query_parameters is not None

    def clean(self):
        super().clean()
        if not self.is_dynamic:
            return

        from icosa.api.filters import validate_asset_query_parameters

        validate_asset_query_parameters(self.query_parameters)
        if self.pk and self.collected_assets.exists():
            raise ValidationError(
                {"query_parameters": "Dynamic collections cannot have explicit assets."}
            )

    def get_public_assets(self):
        if self.is_dynamic:
            from icosa.api.filters import assets_from_query_parameters

            return assets_from_query_parameters(self.query_parameters)

        return (
            self.assets.filter(visibility=PUBLIC)
            .exclude(moderation_state__in=MOD_HIDDEN)
            .select_related("owner")
            .prefetch_related("resource_set", "format_set", "tags")
            .order_by(
                "assetcollectionasset__order",
                "assetcollectionasset__create_time",
                "assetcollectionasset__pk",
            )
        )

    def get_asset_count(self):
        return self.get_public_assets().count()

    def get_displayname(self):
        # Used for compatibiliy with Asset and AssetCollection's methods of the
        # same name.
        return self.name

    def get_thumbnail_url(self):
        thumbnail_url = (
            f"{settings.DEPLOYMENT_SCHEME}{settings.DEPLOYMENT_HOST_WEB}{settings.STATIC_URL}images/nothumbnail.png?v=1"
        )

        if self.image:
            thumbnail_url = self.image.url
        elif asset := self.get_public_assets().first():
            thumbnail_url = asset.get_thumbnail_url()

        return thumbnail_url

    @property
    def moderation_watch_fields(self):
        return [
            "url",
            "name",
            "description",
            "image",
            "query_parameters",
            "markdown",
        ]

    def save(self, *args, **kwargs):
        update_timestamps = kwargs.pop("update_timestamps", False)
        bypass_custom_logic = kwargs.pop("bypass_custom_logic", False)
        bypass_moderation_logging = kwargs.pop("bypass_moderation_logging", False)
        if self._state.adding and not self.url:
            self.url = secrets.token_urlsafe(8)
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
                    self.previous_moderation_state = self.moderation_state
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
        return reverse(
            "icosa:asset_collection_view",
            kwargs={
                "collection_url": self.url,
            },
        )

    def __str__(self):
        return self.name or ""

    class Meta:
        indexes = [
            models.Index(fields=["moderation_state"]),
        ]


class FeaturedCollection(models.Model):
    collection = models.OneToOneField(
        AssetCollection,
        on_delete=models.CASCADE,
        related_name="featured_listing",
    )
    order = models.PositiveIntegerField(default=0)

    def __str__(self):
        return str(self.collection)

    class Meta:
        ordering = ("order", "pk")


class AssetCollectionAsset(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE)
    collection = models.ForeignKey(AssetCollection, on_delete=models.CASCADE, related_name="collected_assets")
    create_time = models.DateTimeField(auto_now_add=True)
    order = models.PositiveIntegerField(default=0)

    def clean(self):
        super().clean()
        if self.collection_id and self.collection.is_dynamic:
            raise ValidationError(
                "Assets cannot be added explicitly to a dynamic collection."
            )

    def __str__(self):
        return f"{self.order}: {self.asset.name}"

    class Meta:
        ordering = ("order",)
