from b2sdk._internal.exception import FileNotHidden, FileNotPresent

from django.db import models
from icosa.helpers.storage import get_b2_bucket

from .common import FILENAME_MAX_LENGTH


class HiddenMediaFileLog(models.Model):
    original_asset_id = models.BigIntegerField()
    file_name = models.CharField(max_length=FILENAME_MAX_LENGTH)
    deleted_from_source = models.BooleanField(default=False)

    def unhide(self):
        bucket = get_b2_bucket()
        try:
            bucket.unhide_file(self.file_name)
        except FileNotPresent:
            print("File not present in storage, marking as deleted")
            self.deleted_from_source = True
            self.save()
        except FileNotHidden:
            print("File already not hidden, nothing to do.")

    def __str__(self):
        return f"{self.original_asset_id}: {self.file_name}"


class BulkSaveLog(models.Model):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    KILLED = "KILLED"
    RESUMED = "RESUMED"

    BULK_SAVE_STATUS_CHOICES = [
        (SUCCEEDED, "Succeeded"),
        (FAILED, "Failed"),
        (KILLED, "Killed"),
        (RESUMED, "Resumed"),
    ]
    create_time = models.DateTimeField(auto_now_add=True)
    update_time = models.DateTimeField(auto_now=True)
    finish_time = models.DateTimeField(null=True, blank=True)
    finish_status = models.CharField(
        max_length=9,
        null=True,
        blank=True,
        choices=BULK_SAVE_STATUS_CHOICES,
    )
    kill_sig = models.BooleanField(default=False)
    last_id = models.BigIntegerField(null=True, blank=True)
