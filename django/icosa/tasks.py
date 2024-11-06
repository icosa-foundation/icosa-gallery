from typing import List, Optional

from huey import signals
from huey.contrib.djhuey import db_task, on_commit_task, signal
from icosa.api.schema import AssetFinalizeData
from icosa.helpers.file import upload_asset, upload_format
from icosa.models import Asset, PolyFormat, User
from ninja import File
from ninja.files import UploadedFile

from django.utils import timezone


@signal(signals.SIGNAL_ERROR)
def task_error(signal, task, exc):
    if task.name == "queue_upload_asset":
        handle_upload_error(task)


def handle_upload_error(task):
    asset = task.kwargs.pop("asset")
    user = task.kwargs.pop("current_user")

    # TODO, instead of writing to a log file, we need to write to some kind of
    # user-facing error log. The design for this needs to be decided? E.g. how
    # will the user dismiss the error, or will we dismiss it after it has been
    # viewed? How do we know it's been read?
    with open("huey_task_error.log", "a") as logfile:
        logfile.write(
            f"{timezone.now()} {asset.id} {user.id} {user.displayname}\n"
        )


@db_task()
def queue_upload_asset(
    current_user: User,
    asset: Asset,
    files: Optional[List[UploadedFile]] = File(None),
) -> str:

    upload_asset(
        current_user,
        asset,
        files,
    )


@on_commit_task()
def queue_upload_format(
    current_user: User,
    asset: Asset,
    files: Optional[List[UploadedFile]] = File(None),
):
    upload_format(
        current_user,
        asset,
        files,
    )


@on_commit_task()
def queue_finalize_asset(asset_url: str, data: AssetFinalizeData):

    asset = Asset.objects.get(url=asset_url)

    # Clean up formats with no root resource.
    # TODO(james): This can probably be done in one query
    resources = asset.polyresource_set.filter(file="")
    format_pks = list(set([x.format.pk for x in resources]))
    formats = PolyFormat.objects.filter(pk__in=format_pks)
    formats.delete()

    # Apply triangle counts to all formats and resources.

    non_tri_roles = [1, 7]  # Original OBJ, BLOCKS

    non_triangulated_formats = asset.polyformat_set.filter(
        role__in=non_tri_roles
    )
    for format in non_triangulated_formats:
        format.triangle_count = data.objPolyCount
        format.save()

    triangulated_formats = asset.polyformat_set.exclude(role__in=non_tri_roles)
    for format in triangulated_formats:
        format.triangle_count = data.triangulatedObjPolyCount
        format.save()

    asset.remix_ids = getattr(data, "remixIds", None)
    asset.save()
