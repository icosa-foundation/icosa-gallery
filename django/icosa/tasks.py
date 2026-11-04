import logging
import time
from typing import (
    List,
    Optional,
)

from django.db import transaction
from django.utils import timezone
from huey import (
    crontab,
    signals,
)
from huey.contrib.djhuey import (
    db_periodic_task,
    db_task,
    signal,
)
from huey.exceptions import CancelExecution
from icosa.api.schema import AssetMetaData
from icosa.helpers.upload import upload_api_asset
from icosa.models import (
    ASSET_STATE_FAILED,
    Asset,
    BulkSaveLog,
    Format,
    ModerationNotification,
    User,
)
from icosa.models.format import is_permanent_localize_error
from ninja import (
    File,
    Form,
)
from ninja.files import UploadedFile

logger = logging.getLogger("django")


@signal(signals.SIGNAL_ERROR)
def task_error(signal, task, exc):
    if task.name == "queue_upload_asset":
        handle_upload_error(task, exc)


def handle_upload_error(task, exc):
    asset = task.kwargs.pop("asset")
    user = task.kwargs.pop("current_user")

    asset.state = ASSET_STATE_FAILED
    asset.save(bypass_moderation_logging=True)

    # TODO, instead of writing to a log file, we need to write to some kind of
    # user-facing error log. The design for this needs to be decided. E.g. how
    # will the user dismiss the error, or will we dismiss it after it has been
    # viewed? How do we know it's been read?
    with open("huey_task_error.log", "a") as logfile:
        logfile.write(f"{timezone.now()} {asset.id} {user.id} {user.displayname}\n")


@db_task()
async def queue_upload_api_asset(
    current_user: User,
    asset: Asset,
    data: Form[AssetMetaData],
    files: Optional[List[UploadedFile]] = File(None),
    skip_thumbnail: bool = False,
) -> str:
    await upload_api_asset(
        asset,
        data,
        files,
        skip_thumbnail,
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
                asset.save(bypass_moderation_logging=True)
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


@db_periodic_task(crontab(minute="*/1"))
def try_send_moderation_notifications():
    ModerationNotification.try_send()


def localize_format(format_id: int) -> int:
    """Pull a format's externally-hosted files into our storage, then
    recalculate its asset's is_viewer_compatible, which is the point of doing
    this. Returns the number of resources localized."""
    format = Format.objects.select_related("asset", "root_resource").get(pk=format_id)
    localized = format.localize_external_resources()
    asset = format.asset
    # Only update this one field; a full save() recomputes rank, search text
    # and other denorms that this task has no business touching.
    Asset.objects.filter(pk=asset.pk).update(is_viewer_compatible=asset.calc_is_viewer_compatible())
    return len(localized)


# One task per format so a failure only affects that format, and so retries
# don't redo work already done (localize_external_resources is idempotent).
# Slow hosts such as archive.org fail intermittently, hence the generous retry
# delay; permanent failures are not retried, since each retry re-downloads the
# whole format. Negative priority so user uploads (default priority 0) waiting
# in the queue are always picked first.
@db_task(retries=3, retry_delay=600, priority=-10)
def queue_localize_format(format_id: int) -> int:
    try:
        return localize_format(format_id)
    except Exception as e:
        if is_permanent_localize_error(e):
            logger.error(f"[localize] Format {format_id} failed and will not be retried: {e}")
            raise CancelExecution(retry=False) from e
        raise
