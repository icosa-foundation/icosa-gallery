import time
from typing import (
    List,
    Optional,
)

from django.db import transaction
from django.utils import timezone
from huey import signals
from huey.contrib.djhuey import (
    db_task,
    signal,
)
from ninja import (
    File,
    Form,
)
from ninja.files import UploadedFile

from icosa.api.schema import AssetMetaData
from icosa.helpers.upload import upload_api_asset
from icosa.helpers.upload_web_ui import upload
from icosa.models import (
    ASSET_STATE_FAILED,
    Asset,
    BulkSaveLog,
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
async def queue_upload_asset_web_ui(
    current_user: User,
    asset: Asset,
    files: Optional[List[UploadedFile]] = File(None),
) -> str:
    await upload(
        asset,
        files,
    )


@db_task()
async def queue_upload_api_asset(
    current_user: User,
    asset: Asset,
    data: Form[AssetMetaData],
    files: Optional[List[UploadedFile]] = File(None),
) -> str:
    await upload_api_asset(
        asset,
        data,
        files,
    )


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
