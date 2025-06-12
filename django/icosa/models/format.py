from django.db import models
from django.db.models import Q

from .asset import Asset
from .common import FILENAME_MAX_LENGTH, STORAGE_PREFIX
from .helpers import suffix
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
    is_preferred_for_viewer = models.BooleanField(default=False)
    is_preferred_for_download = models.BooleanField(default=False)

    def add_root_resource(self, resource):
        if not resource.format:
            from icosa.api.exceptions import RootResourceException

            raise RootResourceException("Resource must have a format associated with it.")
        self.root_resource = resource
        resource.format = None
        resource.save()

    def get_all_resources(self, query: Q = Q()):
        resources = self.resource_set.filter(query)
        # We can only union on another queryset, even though we just want one
        # instance.
        root_resources = Resource.objects.filter(pk=self.root_resource.pk)
        resources = resources.union(root_resources)
        return resources

    def get_resource_data(self, resources):
        if all([x.is_cors_allowed and x.remote_host for x in resources]):
            external_files = [x.external_url for x in resources if x.external_url]
            local_files = [f"{STORAGE_PREFIX}{x.file.name}" for x in resources if x.file]
            resource_data = {
                "files_to_zip": external_files + local_files,
                "role": self.role,
            }
        elif all([x.file for x in resources]):
            resource_data = {
                "files_to_zip": [f"{STORAGE_PREFIX}{suffix(x.file.name)}" for x in resources if x.file],
                "role": self.role,
            }
        else:
            resource_data = {}
        return resource_data

    def get_resource_data_by_role(self, resources, role):
        if self.role == "POLYGONE_GLTF_FORMAT":
            # If we hit this branch, we are not clear on if all gltf files work
            # correctly. Try both the original data we ingested and include
            # the suffixed data which attempts to fix any errors. Add some
            # supporting text to make it clear to the user this is the case.
            resource_data = {
                "files_to_zip": [f"{STORAGE_PREFIX}{x.file.name}" for x in resources if x.file],
                "files_to_zip_with_suffix": [f"{STORAGE_PREFIX}{suffix(x.file.name)}" for x in resources if x.file],
                "supporting_text": "Try the alternative download if the original doesn't work for you. We're working to fix this.",
                "role": self.role,
            }
        else:
            resource_data = self.get_resource_data(resources)
        if not resource_data and self.role == "UPDATED_GLTF_FORMAT":
            # If we hit this branch, we have a format which doesn't
            # have an archive url, but also doesn't have local files.
            # At time of writing, we can't create a zip on the client
            # from the archive.org urls because of CORS. So compile a
            # list of files as if the role was 1003 using our suffixed
            # upload.
            try:
                override_format = self.asset.format_set.get(role="POLYGONE_GLTF_FORMAT")
                override_resources = list(override_format.resource_set.all())
                override_format_root = override_format.root_resource
                if override_format_root is not None:
                    if override_format_root.file or override_format_root.external_url:
                        override_resources.append(override_format_root)
                resource_data = {
                    "files_to_zip": [f"{STORAGE_PREFIX}{suffix(x.file.name)}" for x in override_resources if x.file],
                    "role": self.role,
                }
            except (
                Format.DoesNotExist,
                Format.MultipleObjectsReturned,
            ):
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
