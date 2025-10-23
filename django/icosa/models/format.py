from django.db import models
from django.db.models import Q
from django.utils import timezone

from .asset import Asset
from .common import FILENAME_MAX_LENGTH, STORAGE_PREFIX
from .resource import Resource

ROLE_MAX_LENGTH = 255


class Format(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE)
    format_type = models.CharField(max_length=255)
    zip_archive_url = models.CharField(max_length=FILENAME_MAX_LENGTH, null=True, blank=True)
    triangle_count = models.PositiveIntegerField(null=True, blank=True)
    lod_hint = models.PositiveIntegerField(null=True, blank=True)
    role = models.CharField(
        max_length=ROLE_MAX_LENGTH,
        null=True,
        blank=True,
    )
    root_resource = models.ForeignKey(
        "Resource",
        null=True,
        blank=True,
        related_name="root_formats",
        on_delete=models.SET_NULL,
    )
    is_preferred_for_gallery_viewer = models.BooleanField(default=False)
    is_preferred_for_download = models.BooleanField(default=True)

    def add_root_resource(self, resource):
        if not resource.format:
            from icosa.api.exceptions import RootResourceException

            raise RootResourceException("Resource must have a format associated with it.")
        self.root_resource = resource
        resource.format = None
        resource.save()
        self.save()

    def get_all_resources(self, query: Q = Q()):
        resources = self.resource_set.filter(query)
        if self.root_resource:
            # We can only union on another queryset, even though we just want one
            # instance.
            root_resource = Resource.objects.filter(pk=self.root_resource.pk)
            resources = resources.union(root_resource)
        return resources

    def get_resource_data(self, resources):
        if all([x.is_cors_allowed and x.remote_host for x in resources]):
            external_files = [x.external_url for x in resources if x.external_url]
            local_files = [f"{STORAGE_PREFIX}{x.file.name}" for x in resources if x.file]
            resource_data = {
                "files_to_zip": external_files + local_files,
            }
        elif all([x.file for x in resources]):
            resource_data = {
                "files_to_zip": [f"{STORAGE_PREFIX}{x.file.name}" for x in resources if x.file],
            }
        else:
            resource_data = {}
        return resource_data

    def user_label(self):
        # If self.role is None, then we avoid a db lookup by returning early.
        if self.role is None:
            return self.format_type.lower()
        role_label = FormatRoleLabel.objects.filter(role_text=self.role).first()
        if role_label is None:
            return self.format_type.lower()
        return role_label.label

    class Meta:
        indexes = [
            models.Index(
                fields=[
                    "role",
                ]
            )
        ]


class FormatRoleLabel(models.Model):
    """This model is responsible for creating a user-facing label for a
    format's role. There is no requirement for these records to be filled in.
    User-facing format display implementations should either use a format's
    format_type, or a friendly version of role.

    See Format.user_label for an example of an implementation.
    """

    create_time = models.DateTimeField()
    update_time = models.DateTimeField(null=True, blank=True)
    role_text = models.CharField(max_length=ROLE_MAX_LENGTH)
    label = models.CharField(max_length=1024)

    def save(self, *args, **kwargs):
        update_timestamps = kwargs.pop("update_timestamps", True)
        now = timezone.now()
        if self._state.adding:
            self.create_time = now
        else:
            if update_timestamps:
                self.update_time = now
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.role_text} => {self.label}"
