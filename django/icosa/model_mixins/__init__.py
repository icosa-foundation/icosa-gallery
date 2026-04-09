from django.db import models

MOD_LEGACY = "LEGACY"
MOD_NEW = "NEW"
MOD_APPROVED = "APPROVED"
MOD_DEFERRED = "DEFERRED"
MOD_REJECTED = "REJECTED"
MOD_QUERIED = "QUERIED"
MOD_REPORTED = "REPORTED"
MOD_MODIFIED = "MODIFIED"
MOD_HIDDEN = [MOD_REJECTED, MOD_QUERIED, MOD_REPORTED]
MOD_VISIBLE = [None, MOD_LEGACY, MOD_NEW, MOD_APPROVED, MOD_MODIFIED]

MODERATION_STATE_CHOICES = [
    (MOD_LEGACY, "Legacy"),
    (MOD_NEW, "New"),
    (MOD_APPROVED, "Approved"),
    (MOD_DEFERRED, "Deferred"),
    (MOD_REJECTED, "Rejected"),
    (MOD_QUERIED, "Queried"),
    (MOD_REPORTED, "Reported"),
    (MOD_MODIFIED, "Modified"),
]


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

    @property
    def moderation_watch_fields(self):
        raise NotImplementedError

    class Meta:
        abstract = True
