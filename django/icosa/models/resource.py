from urllib.parse import urlparse

from constance import config
from django.db import models

from .asset import Asset
from .common import (
    FILENAME_MAX_LENGTH,
)
from .helpers import format_upload_path


class Resource(models.Model):
    asset = models.ForeignKey(Asset, null=True, blank=False, on_delete=models.CASCADE)
    format = models.ForeignKey("Format", null=True, blank=True, on_delete=models.CASCADE)
    contenttype = models.CharField(max_length=255, null=True, blank=False)
    file = models.FileField(
        null=True,
        blank=True,
        max_length=FILENAME_MAX_LENGTH,
        upload_to=format_upload_path,
    )
    external_url = models.CharField(max_length=FILENAME_MAX_LENGTH, null=True, blank=True)

    @property
    def url(self):
        url_str = None
        if self.file:
            url_str = self.file.url
        elif self.external_url:
            url_str = self.external_url
        return url_str

    @property
    def internal_url_or_none(self):
        if self.file:
            return self.file.url
        return None

    @property
    def relative_path(self):
        file_name = None
        if self.file:
            file_name = self.file.name.split("/")[-1]
        elif self.external_url:
            file_name = self.external_url.split("/")[-1]
        return file_name

    @property
    def content_type(self):
        return self.file.content_type if self.file else self.contenttype

    @property
    def remote_host(self):
        if self.external_url:
            return urlparse(self.external_url).netloc
        else:
            return None

    @property
    def is_cors_allowed(self):
        if config.EXTERNAL_MEDIA_CORS_ALLOW_LIST:
            allowed_sources = tuple([x.strip() for x in config.EXTERNAL_MEDIA_CORS_ALLOW_LIST.split(",")])
        else:
            allowed_sources = tuple([])
        if self.remote_host is None:
            # Local files (those served by Django storages) are always
            # considered cors-friendly.
            return True
        return self.remote_host in allowed_sources
