import datetime
from typing import List

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.sites.models import Site
from django.db import models, transaction
from django.template.defaultfilters import pluralize
from django.urls import reverse
from django.utils import timezone
from icosa.helpers.email import spawn_send_html_mail

from .common import (
    MOD_MODIFIED,
    MOD_NEW,
    MOD_REPORTED,
    MODERATION_STATE_CHOICES,
)

MOD_STATES_OF_INTEREST = [MOD_MODIFIED, MOD_NEW, MOD_REPORTED]


def get_objects_to_moderate() -> List:
    # Local import to avoid cyclic imports
    from icosa.models import Asset, AssetCollection, AssetOwner

    assets = Asset.objects.filter(moderation_state__in=MOD_STATES_OF_INTEREST)
    collections = AssetCollection.objects.filter(moderation_state__in=MOD_STATES_OF_INTEREST)
    owners = AssetOwner.objects.filter(moderation_state__in=MOD_STATES_OF_INTEREST)

    qs = list(assets) + list(collections) + list(owners)
    objects_to_moderate = sorted(
        qs,
        key=lambda x: (
            x.moderation_state_change_time if x.moderation_state_change_time else datetime.datetime(1970, 1, 1)
        ),
    )
    return objects_to_moderate


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
        db_default="NEW",
    )
    moderation_state_change_time = models.DateTimeField(null=True, blank=True)
    moderation_state_change_by = models.ForeignKey(
        "User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    moderation_changed_fields = models.JSONField(null=True, blank=True)

    class Meta:
        abstract = True


NOTIFICATION_PERIOD_MINUTES = 10080  # 1 week


class ModerationNotification(models.Model):
    sent = models.DateTimeField()
    recipients = models.JSONField()

    @classmethod
    def try_send(cls):
        # Local `User` import to prevent circular imports and User not yet
        # being installed
        User = get_user_model()

        cutoff_time = timezone.now() - datetime.timedelta(minutes=NOTIFICATION_PERIOD_MINUTES)
        notifications = cls.objects.filter(
            sent__gte=cutoff_time,
        )

        # We have sent a digest within the notification period; give up for now.
        if notifications:
            return

        current_site = Site.objects.get_current()
        obj_count = len(get_objects_to_moderate())
        subject = f"Icosa Gallery - moderation required for {obj_count} item{pluralize(obj_count)}"
        html = f"<p>Please go to <a href='https://{current_site.domain}{reverse('icosa:moderation_queue')}'>the moderation queue</a> and approve or reject the latest changes.</p>"
        html = f"<html><body>{html}</body></html>"

        moderators = User.objects.filter(groups__name__in=["Moderator"])
        if not moderators:
            return
        recipients = [x.email for x in moderators]

        spawn_send_html_mail(subject, html, recipients)

        cls.objects.create(
            sent=timezone.now(),
            recipients=recipients,
        )

    def __str__(self):
        date_str = self.sent.strftime("%d/%m/%Y %H:%M:%S")
        recipients = (", ").join(self.recipients)
        return f"{date_str} to {recipients}"
