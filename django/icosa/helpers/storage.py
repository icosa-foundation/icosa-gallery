from b2sdk.v2 import B2Api, InMemoryAccountInfo

from django.conf import settings


def get_b2_bucket():
    info = InMemoryAccountInfo()
    b2_api = B2Api(info)
    b2_api.authorize_account(
        "production",
        settings.DJANGO_STORAGE_ACCESS_KEY,
        settings.DJANGO_STORAGE_SECRET_KEY,
    )
    bucket = b2_api.get_bucket_by_name("icosa-gallery")
    return bucket
