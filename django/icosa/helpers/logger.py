from typing import NoReturn, Optional

from django.utils import timezone


def log(message: str, logname: Optional[str] = None, logfile: Optional[str] = None) -> NoReturn:
    try:
        if logfile is None:
            logfile = "django_log"
        logfile = f"logs/{logfile}"
        now = timezone.now().strftime("%d/%m/%Y %H:%M:%S:%f %z")
        with open(logfile, "a") as f:
            f.write(f"{now} - {message}\n")

    except Exception:
        pass
