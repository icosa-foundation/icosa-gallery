from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models, transaction
from django.utils import timezone

from .common import MODERATION_STATE_CHOICES


class ModerationEvent(models.Model):
    create_time = models.DateTimeField()
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.BigIntegerField()
    source_object = GenericForeignKey("content_type", "object_id")
    state = models.CharField(
        max_length=255,
        choices=MODERATION_STATE_CHOICES,
        default="NEW",
        db_default="New",
    )
    data = models.JSONField()
    user = models.ForeignKey(
        "User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="moderation_events",
    )
    notes = models.TextField(null=True, blank=True)

    @transaction.atomic
    def save(self, *args, **kwargs):
        now = timezone.now()
        if self._state.adding:
            self.create_time = now
        super().save(*args, **kwargs)

    class Meta:
        indexes = [models.Index(fields=["content_type", "object_id"])]


class ModerationMixin(models.Model):
    moderation_state = models.CharField(
        max_length=255,
        choices=MODERATION_STATE_CHOICES,
        default="NEW",
        db_default="New",
    )
    moderation_state_change_time = models.DateTimeField(null=True, blank=True)
    moderation_state_change_by = models.ForeignKey(
        "User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="moderated_assets",
    )
    moderation_changed_fields = models.JSONField(null=True, blank=True)

    class Meta:
        abstract = True
