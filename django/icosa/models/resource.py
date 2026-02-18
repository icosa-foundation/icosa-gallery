from typing import Optional
from urllib.parse import urlparse

from constance import config
from django.conf import settings
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
    uploaded_file_path = models.CharField(max_length=FILENAME_MAX_LENGTH, null=True, blank=True)
    file = models.FileField(
        null=True,
        blank=True,
        max_length=FILENAME_MAX_LENGTH,
        upload_to=format_upload_path,
    )
    external_url = models.CharField(max_length=FILENAME_MAX_LENGTH, null=True, blank=True)
    hide_from_downloads = models.BooleanField(default=False)

    @property
    def url(self) -> Optional[str]:
        if self.file:
            storage = settings.DJANGO_STORAGE_URL
            bucket = settings.DJANGO_STORAGE_BUCKET_NAME
            url_str = f"{storage}/{bucket}/{self.file.name}"
            return url_str
        elif self.external_url:
            return self.external_url
        return None

    @property
    def internal_or_cors_url(self):
        if self.file:
            return self.file.url
        if self.is_cors_allowed:
            return self.external_url
        return None

    @property
    def relative_path(self):
        file_name = ""
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
    def external_file_name(self):
        if self.external_url:
            return self.external_url.split("/")[-1]
        else:
            return None

    @property
    def extension(self):
        if self.external_url:
            return self.external_url.split(".")[-1]
        else:
            return self.file.name.split(".")[-1]

    @property
    def is_cors_allowed(self):
        remote_host = self.remote_host
        if remote_host is None:
            return True
        if config.EXTERNAL_MEDIA_CORS_ALLOW_LIST:
            allowed_sources = tuple([x.strip() for x in config.EXTERNAL_MEDIA_CORS_ALLOW_LIST.split(",")])
            return remote_host in allowed_sources
        return False
