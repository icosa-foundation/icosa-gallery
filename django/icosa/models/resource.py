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
        """
        This function currently returns the resource's local file url or its external url. If the latter, we need to substitute out archive.org urls that link to an interstitial web page with our best guess at a link to the resource of the same type.
        """
        if self.file:
            storage = settings.DJANGO_STORAGE_URL
            bucket = settings.DJANGO_STORAGE_BUCKET_NAME
            url_str = f"{storage}/{bucket}/{self.file.name}"
        elif self.external_url:
            ext_url = self.external_url
            prefix = "https://web.archive.org/web/"
            decider = "https://"
            if ext_url.startswith(f"{prefix}{decider}"):
                # If we are here it means we are linking to a non snapshotted
                # version of the file, and so are returning a link to an html
                # page. We need to force linking to a snapshot, so create a
                # fake timestamp to guess at a snapshot. Archive.org, at time
                # of writing, will notice there is no snapshot at that time,
                # and will return a redirect to the latest snapshot it has.
                #
                # Clients will need to follow redirects for this to work
                # properly for them.
                fake_timestamp_path = "20250101010101id_/"
                url_str = f"{prefix}{fake_timestamp_path}{ext_url[len(prefix) :]}"
            else:
                url_str = ext_url
        else:
            url_str = ""
        return url_str

    @property
    def internal_or_cors_url(self):
        if self.file:
            return self.file.url
        if self.is_cors_allowed:
            return self.external_url
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
        remote_host = self.remote_host
        if remote_host is None:
            return True
        if config.EXTERNAL_MEDIA_CORS_ALLOW_LIST:
            allowed_sources = tuple([x.strip() for x in config.EXTERNAL_MEDIA_CORS_ALLOW_LIST.split(",")])
            return remote_host in allowed_sources
        return False
