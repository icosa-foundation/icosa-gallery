import time
from typing import List, Optional

from django.utils import timezone
from huey import signals
from huey.contrib.djhuey import db_task, on_commit_task, signal
from icosa.api.schema import AssetFinalizeData
from icosa.helpers.file import upload_blocks_format
from icosa.helpers.upload import upload_api_asset
from icosa.helpers.upload_web_ui import upload
from icosa.models import (
    ASSET_STATE_COMPLETE,
    ASSET_STATE_FAILED,
    Asset,
    AssetOwner,
    BulkSaveLog,
    Format,
)
from ninja import File
from ninja.files import UploadedFile


@signal(signals.SIGNAL_ERROR)
def task_error(signal, task, exc):
    if task.name == "queue_upload_asset":
        handle_upload_error(task, exc)


def handle_upload_error(task, exc):
    asset = task.kwargs.pop("asset")
    user = task.kwargs.pop("current_user")

    asset.state = ASSET_STATE_FAILED
    asset.save(update_timestamps=False)

    # TODO, instead of writing to a log file, we need to write to some kind of
    # user-facing error log. The design for this needs to be decided. E.g. how
    # will the user dismiss the error, or will we dismiss it after it has been
    # viewed? How do we know it's been read?
    with open("huey_task_error.log", "a") as logfile:
        logfile.write(f"{timezone.now()} {asset.id} {user.id} {user.displayname}\n")


@db_task()
def queue_upload_asset_web_ui(
    current_user: AssetOwner,
    asset: Asset,
    files: Optional[List[UploadedFile]] = File(None),
) -> str:
    upload(
        current_user,
        asset,
        files,
    )


@db_task()
def queue_upload_api_asset(
    current_user: AssetOwner,
    asset: Asset,
    files: Optional[List[UploadedFile]] = File(None),
) -> str:
    upload_api_asset(
        current_user,
        asset,
        files,
    )


@on_commit_task()
def queue_blocks_upload_format(
    current_user: AssetOwner,
    asset: Asset,
    files: Optional[List[UploadedFile]] = File(None),
):
    upload_blocks_format(
        current_user,
        asset,
        files,
    )


@on_commit_task()
def queue_finalize_asset(asset_url: str, data: AssetFinalizeData):
    asset = Asset.objects.get(url=asset_url)

    # Clean up formats with no root resource.
    # TODO(james): This can probably be done in one query
    resources = asset.resource_set.filter(file="")
    format_pks = list(set([x.format.pk for x in resources]))
    formats = Format.objects.filter(pk__in=format_pks)
    formats.delete()

    # Apply triangle counts to all formats and resources.

    non_tri_roles = [1, 7]  # Original OBJ, BLOCKS

    non_triangulated_formats = asset.format_set.filter(role__in=non_tri_roles)
    for format in non_triangulated_formats:
        format.triangle_count = data.objPolyCount
        format.save()

    triangulated_formats = asset.format_set.exclude(role__in=non_tri_roles)
    for format in triangulated_formats:
        format.triangle_count = data.triangulatedObjPolyCount
        format.save()

    asset.state = ASSET_STATE_COMPLETE
    asset.remix_ids = getattr(data, "remixIds", None)
    asset.save(update_timestamps=False)


def save_all_assets(
    resume: bool = False,
    verbose: bool = False,
):
    save_log = None
    if resume:
        save_log = BulkSaveLog.objects.filter(
            finish_status=BulkSaveLog.KILLED,
        ).last()

    if save_log is None:
        save_log = BulkSaveLog.objects.create()
    else:
        save_log.finish_status = BulkSaveLog.RESUMED
        save_log.kill_sig = False
        save_log.save()

    if save_log.last_id:
        assets = Asset.objects.filter(pk__gt=save_log.last_id)
    else:
        assets = Asset.objects.all()

    for asset in assets.order_by("pk").iterator(chunk_size=1000):
        save_log.refresh_from_db()
        if save_log.kill_sig is True or save_log.finish_status == BulkSaveLog.FAILED:
            save_log.finish_status = BulkSaveLog.KILLED
            save_log.finish_time = timezone.now()
            save_log.save()
            if verbose:
                print(f"Process killed. Last updated: {save_log.last_id}")
            return
        try:
            asset.save(update_timestamps=False)
            if verbose:
                print(f"Saved Asset {asset.id}\t", end="\r")
            save_log.last_id = asset.id
            save_log.save(update_fields=["update_time", "last_id"])
            time.sleep(1)
        except Exception:
            save_log.finish_status = BulkSaveLog.FAILED
            save_log.finish_time = timezone.now()
            save_log.save()
            return

    save_log.finish_status = BulkSaveLog.SUCCEEDED
    save_log.finish_time = timezone.now()
    save_log.save()


@db_task()
def queue_save_all_assets(
    resume: bool = False,
):
    save_all_assets(resume)
