import inspect
from typing import Optional

from django.utils import timezone


def icosa_log(message: Optional[str] = None, logfile: Optional[str] = None) -> None:
    try:
        now = timezone.now().strftime("%d/%m/%Y %H:%M:%S:%f %z")

        if logfile is None:
            logfile = "django_log"
        logfile = f"logs/{logfile}"

        if message is None:
            message = "(No message supplied)"

        curframe = inspect.currentframe()
        calframe = inspect.getouterframes(curframe, 2)
        fn_name = calframe[1][3]

        with open(logfile, "a") as f:
            f.write(f"{now} - {fn_name} - {message}\n")

    except Exception:
        pass
