from asgiref.sync import sync_to_async
from constance import config


@sync_to_async
def aconfig(field: str):
    return getattr(config, field)
