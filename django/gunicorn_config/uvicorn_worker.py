from uvicorn_worker import UvicornWorker as BaseUvicornWorker


# Django does not support Lifespan Protocol
# https://asgi.readthedocs.io/en/latest/specs/lifespan.html
# https://github.com/django/django/pull/13636
# https://code.djangoproject.com/ticket/31508
# Using uvicorn.workers.UvicornWorker throws INFO warning:
#   "ASGI 'lifespan' protocol appears unsupported."
# To avoid that we need to disable 'lifespan' in the worker
class UvicornWorker(BaseUvicornWorker):
    CONFIG_KWARGS = {"lifespan": "off"}
