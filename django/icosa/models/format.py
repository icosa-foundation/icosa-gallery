from django.db import models
from django.db.models import Q

from .asset import Asset
from .common import FILENAME_MAX_LENGTH, STORAGE_PREFIX
from .resource import Resource


class Format(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE)
    format_type = models.CharField(max_length=255)
    zip_archive_url = models.CharField(max_length=FILENAME_MAX_LENGTH, null=True, blank=True)
    triangle_count = models.PositiveIntegerField(null=True, blank=True)
    lod_hint = models.PositiveIntegerField(null=True, blank=True)
    role = models.CharField(
        max_length=255,
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
    hide_from_downloads = models.BooleanField(default=False)

    def add_root_resource(self, resource):
        if not resource.format:
            from icosa.api.exceptions import RootResourceException

            raise RootResourceException("Resource must have a format associated with it.")
        self.root_resource = resource
        resource.format = None
        resource.save()

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

    class Meta:
        indexes = [
            models.Index(
                fields=[
                    "role",
                ]
            )
        ]
