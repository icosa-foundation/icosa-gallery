import time
from typing import (
    Dict,
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
from icosa.api.schema import AssetMetaData
from icosa.helpers.gltf_transform import transform_asset_formats
from icosa.helpers.upload import upload_api_asset
from icosa.models import (
    ASSET_STATE_COMPLETE,
    ASSET_STATE_FAILED,
    ASSET_STATE_UPLOADING,
    Asset,
    BulkSaveLog,
    ModerationNotification,
    User,
)
from ninja import (
    File,
    Form,
)
from ninja.files import UploadedFile


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


@db_task()
def queue_gltf_transform(
    asset: Asset,
    operations: List[str],
    format_types: Optional[List[str]] = None,
    options: Optional[Dict] = None,
) -> Dict:
    """
    Queue a glTF transformation task.

    Args:
        asset: The Asset instance to transform
        operations: List of operations to apply
        format_types: List of format types to transform (optional)
        options: Operation-specific options (optional)

    Returns:
        Dictionary containing transformation results
    """
    try:
        # Set asset state to uploading (processing)
        asset.state = ASSET_STATE_UPLOADING
        asset.save(update_timestamps=False)

        # Perform the transformation
        results = transform_asset_formats(
            asset=asset,
            operations=operations,
            options=options,
            format_types=format_types,
        )

        # Check if all transformations were successful
        all_success = all(result.get("success", False) for result in results.values())

        if all_success:
            asset.state = ASSET_STATE_COMPLETE
        else:
            asset.state = ASSET_STATE_FAILED

        asset.save(update_timestamps=True)

        return {
            "success": all_success,
            "results": results,
        }

    except Exception as e:
        asset.state = ASSET_STATE_FAILED
        asset.save(update_timestamps=False)
        return {
            "success": False,
            "error": str(e),
        }


@db_periodic_task(crontab(minute="*/1"))
def try_send_moderation_notifications():
    ModerationNotification.try_send()
