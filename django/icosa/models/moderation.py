import datetime

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.sites.models import Site
from django.db import models, transaction
from django.template.defaultfilters import pluralize
from django.urls import reverse
from django.utils import timezone
from icosa.helpers.email import spawn_send_html_mail
from icosa.helpers.moderation import get_objects_to_moderate
from icosa.model_mixins import MODERATION_STATE_CHOICES


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


NOTIFICATION_PERIOD_MINUTES = 10080  # 1 week


class ModerationNotification(models.Model):
    sent = models.DateTimeField()
    recipients = models.JSONField()

    @classmethod
    def try_send(cls):
        # Local `User` import to prevent circular imports and User not yet
        # being installed
        User = get_user_model()

        now = timezone.now()
        cutoff_time = now - datetime.timedelta(minutes=NOTIFICATION_PERIOD_MINUTES)
        notifications = cls.objects.filter(sent__gte=cutoff_time)

        # We have sent a digest within the notification period; give up for now.
        if notifications:
            return

        objects_to_moderate = get_objects_to_moderate()
        obj_count = objects_to_moderate.count()

        # There is nothing to review; give up for now.
        if obj_count == 0:
            return

        is_urgent = False
        last_obj = objects_to_moderate.fetch_one(last=True)
        if last_obj is not None:
            timestamp = (
                last_obj.moderation_state_change_time
                if last_obj.moderation_state_change_time
                else last_obj.update_time
                if last_obj.update_time
                else last_obj.create_time
            )
            if timestamp < cutoff_time:
                is_urgent = True

        current_site = Site.objects.get_current()
        subject = f"Icosa Gallery - moderation required for {obj_count} item{pluralize(obj_count)}"
        if is_urgent:
            subject = f"URGENT! {subject}"
        html = f"<p>Please go to <a href='https://{current_site.domain}{reverse('icosa:moderation_queue')}'>the moderation queue</a> and approve or reject the latest changes.</p>"
        html = f"<html><body>{html}</body></html>"

        moderators = User.objects.filter(groups__name__in=["Moderator"])
        recipients = [x.email for x in moderators]
        if is_urgent:
            admin_email = getattr(settings, "ADMIN_EMAIL", None)
            if admin_email is not None:
                recipients.append(admin_email)

        spawn_send_html_mail(subject, html, recipients)

        cls.objects.create(
            sent=timezone.now(),
            recipients=recipients,
        )

    def __str__(self):
        date_str = self.sent.strftime("%d/%m/%Y %H:%M:%S")
        recipients = (", ").join(self.recipients)
        return f"{date_str} to {recipients}"
