from typing import List, Optional

from huey.contrib.djhuey import db_task
from icosa.helpers.file import upload_asset
from icosa.models import User
from ninja import File
from ninja.files import UploadedFile


@db_task()
def queue_upload(
    current_user: User,
    job_snowflake: int,
    files: Optional[List[UploadedFile]] = File(None),
    thumbnail: UploadedFile = File(...),
):
    upload_asset(
        current_user,
        job_snowflake,
        files,
        None,
    )
