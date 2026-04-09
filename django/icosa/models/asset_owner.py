import logging

from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser
from django.db import models, transaction
from django.db.models import QuerySet
from django.urls import reverse
from django.utils import timezone
from icosa.model_mixins import (
    MOD_DEFERRED,
    MOD_MODIFIED,
    MOD_NEW,
    ModerationMixin,
)

logger = logging.getLogger("django")


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


class AssetOwner(ModerationMixin):
    create_time = models.DateTimeField()
    update_time = models.DateTimeField(null=True, blank=True)
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
        related_name="merged_owners",
    )
    # `moderation_state_change_by` is defined in this model's superclass, but
    # the default related name clashes with `django_user`, so we must define it
    # again here.
    moderation_state_change_by = models.ForeignKey(
        "User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="moderated_owners",
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

    @property
    def moderation_watch_fields(self):
        return [
            "url",
            "displayname",
            "description",
        ]

    @transaction.atomic
    def save(self, *args, **kwargs):
        update_timestamps = kwargs.pop("update_timestamps", False)
        bypass_custom_logic = kwargs.pop("bypass_custom_logic", False)
        bypass_moderation_logging = kwargs.pop("bypass_moderation_logging", False)

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
                    original_instance = AssetOwner.objects.get(pk=self.pk)
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

    def __str__(self):
        return self.displayname

    class Meta:
        indexes = [
            models.Index(fields=["moderation_state"]),
        ]
