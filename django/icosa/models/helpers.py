import os
import tempfile
import time
from pathlib import Path

from constance import config
from django.conf import settings
from django.core.cache import cache
import requests

# (connect, read) timeouts in seconds. Read timeout is per-chunk, not total,
# so large files from slow hosts such as archive.org are fine.
EXTERNAL_DOWNLOAD_TIMEOUT = (30, 300)
EXTERNAL_DOWNLOAD_RETRIES = 5
EXTERNAL_DOWNLOAD_CHUNK_SIZE = 1024 * 1024


def get_cloud_media_root():
    if settings.DJANGO_STORAGE_MEDIA_ROOT is not None:
        return f"{settings.DJANGO_STORAGE_MEDIA_ROOT}/"
    else:
        # We are writing to whatever is defined in settings.MEDIA_ROOT.
        return ""


def suffix(name):
    if name is None:
        return None
    if name.endswith("_%28GLTFupdated%29.gltf"):
        return name
    if name.endswith(".gltf"):
        return "".join([f"{p[0]}_(GLTFupdated){p[1]}" for p in [os.path.splitext(name)]])
    return name


def masthead_image_upload_path(instance, filename):
    root = get_cloud_media_root()
    return f"{root}masthead_images/{instance.id}/{filename}"


def collection_image_upload_path(instance, filename):
    root = get_cloud_media_root()
    return f"{root}collection_images/{instance.id}/{filename}"


def thumbnail_upload_path(instance, filename):
    root = get_cloud_media_root()
    path = f"{root}{instance.owner.id}/{instance.id}/{filename}"
    return path


def preview_image_upload_path(instance, filename):
    root = get_cloud_media_root()
    return f"{root}{instance.owner.id}/{instance.id}/preview_image/{filename}"


def format_upload_path(instance, filename):
    root = get_cloud_media_root()
    format = instance.format
    if format is None:
        # This is a root resource. TODO(james): implement a get_format method
        # that can handle this for us.
        format = instance.root_formats.first()
    asset = instance.asset
    ext = filename.split(".")[-1]
    if instance.format is None:  # proxy test for if this is a root resource.
        name = f"model.{ext}"
    elif ext == "obj" and instance.format.role == "ORIGINAL_TRIANGULATED_OBJ_FORMAT":
        name = f"model-triangulated.{ext}"
    else:
        name = filename

    upload_path = f"{root}{asset.owner.id}/{asset.id}/{format.format_type}/{name}"
    if instance.uploaded_file_path is None:
        return upload_path

    original_path = Path(instance.uploaded_file_path)
    if len(original_path.parents) > 1:
        upload_path = f"{root}{asset.owner.id}/{asset.id}/{format.format_type}/{original_path.parent}/{name}"
    return upload_path


def get_cached_cors_allow_list():
    cache_key = "config_EXTERNAL_MEDIA_CORS_ALLOW_LIST"
    allow_list = cache.get(cache_key, None)
    if allow_list is not None:
        return allow_list

    allow_list = config.EXTERNAL_MEDIA_CORS_ALLOW_LIST
    cache.set(cache_key, allow_list, 60)  # 60 secs, one minute
    return allow_list


def is_transient_download_error(e: requests.RequestException) -> bool:
    """Whether retrying might help: connection problems, timeouts, an
    interrupted transfer, 408, 429 or 5xx. Malformed URLs and other HTTP
    errors will fail the same way every time."""
    if isinstance(e, requests.HTTPError):
        status = e.response.status_code if e.response is not None else None
        return status in (408, 429) or (status is not None and status >= 500)
    return isinstance(e, (requests.ConnectionError, requests.Timeout, requests.exceptions.ChunkedEncodingError))


def download_to_tempfile(
    url,
    timeout=EXTERNAL_DOWNLOAD_TIMEOUT,
    retries=EXTERNAL_DOWNLOAD_RETRIES,
):
    """Stream `url` to a named temporary file on disk and return it, rewound
    to the start. The caller is responsible for closing it (which deletes it).

    Retries with exponential backoff on connection errors, timeouts, 429 and
    5xx responses; other HTTP errors are raised immediately.
    """
    attempt = 0
    while True:
        attempt += 1
        tmp = tempfile.NamedTemporaryFile()
        try:
            with requests.get(url, stream=True, timeout=timeout) as response:
                response.raise_for_status()
                for chunk in response.iter_content(chunk_size=EXTERNAL_DOWNLOAD_CHUNK_SIZE):
                    tmp.write(chunk)
            tmp.flush()
            tmp.seek(0)
            return tmp
        except requests.RequestException as e:
            tmp.close()
            if not is_transient_download_error(e) or attempt > retries:
                raise
            time.sleep(2**attempt)
