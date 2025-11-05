import time
from typing import List, Optional

from huey import signals
from huey.contrib.djhuey import db_task, on_commit_task, signal
from ninja import File
from ninja.files import UploadedFile

from django.db import transaction
from django.utils import timezone
from icosa.api.schema import AssetMetaData
from icosa.helpers.file import upload_blocks_format
from icosa.helpers.logger import icosa_log
from icosa.helpers.upload import upload_api_asset
from icosa.helpers.upload_web_ui import upload
from icosa.models import (
    ASSET_STATE_COMPLETE,
    ASSET_STATE_FAILED,
    Asset,
    BulkSaveLog,
    Format,
    User,
)


@signal(signals.SIGNAL_ERROR)
def task_error(signal, task, exc):
    if task.name == "queue_upload_asset":
        handle_upload_error(task, exc)


def handle_upload_error(task, exc):
    asset = task.kwargs.pop("asset")
    user = task.kwargs.pop("current_user")

    asset.state = ASSET_STATE_FAILED
    asset.save()

    # TODO, instead of writing to a log file, we need to write to some kind of
    # user-facing error log. The design for this needs to be decided. E.g. how
    # will the user dismiss the error, or will we dismiss it after it has been
    # viewed? How do we know it's been read?
    with open("huey_task_error.log", "a") as logfile:
        logfile.write(f"{timezone.now()} {asset.id} {user.id} {user.displayname}\n")


@db_task()
def queue_upload_asset_web_ui(
    current_user: User,
    asset: Asset,
    files: Optional[List[UploadedFile]] = File(None),
) -> str:
    upload(
        asset,
        files,
    )


@db_task()
def queue_upload_api_asset(
    current_user: User,
    asset: Asset,
    files: Optional[List[UploadedFile]] = File(None),
) -> str:
    upload_api_asset(
        asset,
        files,
    )


@on_commit_task()
def queue_blocks_upload_format(
    current_user: User,
    asset: Asset,
    files: Optional[List[UploadedFile]] = File(None),
):
    icosa_log(f"Start upload for asset {asset.url}")
    upload_blocks_format(
        asset,
        files,
    )


@on_commit_task()
@transaction.atomic
def queue_finalize_asset(asset_url: str, data: AssetMetaData):
    start = time.time()  # Logging

    asset = Asset.objects.get(url=asset_url)

    # Clean up formats with no root resource.
    # TODO(james): This can probably be done in one query
    resources = asset.resource_set.filter(file="")
    format_pks_non_root = list(set([x.format.pk for x in resources if x.format]))
    format_pks_root = list(Format.objects.filter(root_resource__in=resources).values_list("pk", flat=True))
    format_pks = format_pks_non_root + format_pks_root
    formats = Format.objects.filter(pk__in=format_pks)
    formats.delete()

    # Apply triangle counts to all formats and resources.

    NON_TRI_ROLES = ["ORIGINAL_OBJ_FORMAT", "BLOCKS_FORMAT"]

    non_triangulated_formats = asset.format_set.filter(role__in=NON_TRI_ROLES)
    for format in non_triangulated_formats:
        format.triangle_count = data.objPolyCount
        format.save()

    triangulated_formats = asset.format_set.exclude(role__in=NON_TRI_ROLES)
    for format in triangulated_formats:
        format.triangle_count = data.triangulatedObjPolyCount
        format.save()

    preferred_format = asset.format_set.filter(role="ORIGINAL_TRIANGULATED_OBJ_FORMAT").first()
    if preferred_format is not None and preferred_format.root_resource and preferred_format.root_resource.file:
        preferred_format.is_preferred_for_gallery_viewer = True
        preferred_format.save()
    asset.state = ASSET_STATE_COMPLETE
    asset.remix_ids = getattr(data, "remixIds", None)
    asset.save()

    end = time.time()  # Logging
    icosa_log(f"Finalized asset {asset.url} in {end - start} seconds.")  # Logging


def save_all_assets(
    resume: bool = False,
    verbose: bool = False,
):
    save_log = None
    if resume:
        save_log = BulkSaveLog.objects.exclude().last()
    elif bool(BulkSaveLog.objects.filter(finish_time=None).count()):
        print(
            "It appears there are already save jobs running. Please wait for them to finish or kill them first with --kill."
        )
        return

    if save_log is None or save_log.finish_status == BulkSaveLog.FAILED:
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
            if not save_log.finish_status == BulkSaveLog.FAILED:
                save_log.finish_status = BulkSaveLog.KILLED
            save_log.finish_time = timezone.now()
            save_log.save()
            if verbose:
                print(f"Process killed. Last updated: {save_log.last_id}")
            return
        try:
            with transaction.atomic():
                asset.save()
                if verbose:
                    print(f"Saved Asset {asset.id}\t", end="\r")
                save_log.last_id = asset.id
                save_log.save(update_fields=["update_time", "last_id"])
            time.sleep(0.05)
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
