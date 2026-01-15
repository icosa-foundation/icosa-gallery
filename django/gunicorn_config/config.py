import multiprocessing
import os

bind = "0.0.0.0:8000"
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "gunicorn_config.uvicorn_worker.UvicornWorker"
worker_connections = 1000
timeout = 900

if os.environ.get("DEPLOYMENT_ENV") in ["development", "local"]:
    reload = True
