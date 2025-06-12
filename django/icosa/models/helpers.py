import os

from django.conf import settings


def get_cloud_media_root():
    if settings.DJANGO_STORAGE_MEDIA_ROOT is not None:
        return f"{settings.DJANGO_STORAGE_MEDIA_ROOT}/"
    else:
        # We are writing to whatever is defined in settings.MEDIA_ROOT.
        return ""


def suffix(name):
    if name is None:
        return None
    if name.endswith(".gltf"):
        return "".join([f"{p[0]}_(GLTFupdated){p[1]}" for p in [os.path.splitext(name)]])
    return name


def masthead_image_upload_path(instance, filename):
    root = get_cloud_media_root()
    return f"{root}masthead_images/{instance.id}/{filename}"


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
    return f"{root}{asset.owner.id}/{asset.id}/{format.format_type}/{name}"
