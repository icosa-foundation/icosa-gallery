"""Backfill `Format.triangle_count` (and the denormed `Asset.triangle_count`)
for assets whose count is currently 0.

A 0 means the uploader's client never reported a triangle count, not that the
model is empty. We recompute it from the stored geometry without downloading
the mesh buffers (see ``icosa.helpers.triangle_count``).

Each asset is measured from a single format (tried in priority order, stopping
at the first success), since the asset's count is the Max across its formats —
one good measurement fixes it, and it keeps redundant fetches off archive.org.

Examples:
    python manage.py backfill_triangle_count --dry-run --limit 20
    python manage.py backfill_triangle_count --workers 16 --archive-rate 5
    python manage.py backfill_triangle_count --asset <asset-url>
"""

import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from django.core.management.base import BaseCommand
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from icosa.helpers.triangle_count import count_triangles
from icosa.models import Asset, Format

LOG_PREFIX = "[backfill_triangle_count]"

# Formats we can measure, in the order we prefer to try them per asset (cheapest
# / most exact first; VOX is an estimate). GLTF1 is intentionally absent — the
# parser does not support 1.0, so trying it would just waste a fetch and fail.
# Everything not listed (TILT, BLOCKS, FBX, splats, ...) is unmeasurable here.
FORMAT_PRIORITY = {"GLB": 0, "GLTF2": 1, "OBJ": 2, "VOX": 3}
SUPPORTED_EXTENSIONS = ("glb", "gltf", "obj", "vox")

ARCHIVE_HOST = "web.archive.org"

_thread_local = threading.local()

# Matches the part after `…/web/` in a Wayback URL: an optional timestamp, an
# optional `id_` raw-mode flag, then the original archived URL.
_WAYBACK_PATH = re.compile(r"^(\d{1,14})?(id_)?/?(https?://.*)$", re.IGNORECASE)


def _fetchable_url(url: str) -> str:
    """Make a stored URL safe to fetch.

    Backblaze URLs are returned unchanged. Wayback Machine URLs are stored
    timestamp-less (so archive.org redirects to the latest snapshot); that
    redirect lands on the HTML *replay* page, which isn't the file and ignores
    Range. Rewriting to the `…/web/<ts>id_/<url>` raw form keeps the
    latest-snapshot behaviour (the placeholder timestamp snaps to the nearest
    capture) while serving the raw archived bytes. Idempotent.
    """
    marker = "/web/"
    if ARCHIVE_HOST not in url or marker not in url:
        return url
    head, _, rest = url.partition(marker)
    match = _WAYBACK_PATH.match(rest)
    if not match:
        return url
    timestamp = match.group(1) or "2"  # placeholder -> nearest snapshot
    original = match.group(3)
    return f"{head}{marker}{timestamp}id_/{original}"


class _RateLimiter:
    """Process-wide minimum spacing between requests, shared across all worker
    threads. Reserves a staggered slot per call and releases the lock before
    sleeping, so N threads self-space rather than serialise."""

    def __init__(self, rate_per_sec: float):
        self._interval = 1.0 / rate_per_sec if rate_per_sec and rate_per_sec > 0 else 0.0
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self) -> None:
        if self._interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            scheduled = max(now, self._next)
            self._next = scheduled + self._interval
        delay = scheduled - time.monotonic()
        if delay > 0:
            time.sleep(delay)


# Reassigned from --archive-rate in handle(); only archive.org traffic uses it.
_archive_limiter = _RateLimiter(0)


class _ThrottledAdapter(HTTPAdapter):
    """Applies the global archive.org rate limit before every request it sends.

    Mounted only for the archive.org host, so Backblaze traffic is unaffected.
    The Retry it carries respects 429 ``Retry-After`` headers (urllib3 default),
    so we throttle proactively and still back off if archive.org pushes back.
    """

    def send(self, request, **kwargs):
        _archive_limiter.wait()
        return super().send(request, **kwargs)


def _session() -> requests.Session:
    """One pooled, retrying Session per worker thread; archive.org throttled."""
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
        )
        default_adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", default_adapter)
        session.mount("https://", default_adapter)
        # Longer-prefix mounts win, so only archive.org goes through the throttle.
        throttled = _ThrottledAdapter(max_retries=retry)
        session.mount(f"https://{ARCHIVE_HOST}/", throttled)
        session.mount(f"http://{ARCHIVE_HOST}/", throttled)
        _thread_local.session = session
    return session


def _format_url(fmt: Format):
    """Fetchable URL of the format's root model file, or ``None``."""
    resource = fmt.root_resource
    if resource is None:
        # Fall back to a non-image resource with a supported extension.
        for candidate in fmt.get_non_image_resources():
            if candidate.url and candidate.url.rsplit(".", 1)[-1].lower() in SUPPORTED_EXTENSIONS:
                resource = candidate
                break
    if resource is None or not resource.url:
        return None
    return _fetchable_url(resource.url)


def _candidates(asset: Asset):
    """(format, url) pairs for an asset, ordered by FORMAT_PRIORITY."""
    found = []
    for fmt in asset.format_set.all():
        priority = FORMAT_PRIORITY.get(fmt.format_type)
        if priority is None:
            continue
        url = _format_url(fmt)
        if url is None:
            continue
        if url.rsplit("?", 1)[0].rsplit(".", 1)[-1].lower() not in SUPPORTED_EXTENSIONS:
            continue
        found.append((priority, fmt, url))
    found.sort(key=lambda item: item[0])
    return [(fmt, url) for _priority, fmt, url in found]


class Command(BaseCommand):
    help = "Recompute triangle counts for assets where the count is 0."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=None, help="Process at most N assets.")
        parser.add_argument("--workers", type=int, default=8, help="Concurrent asset fetches.")
        parser.add_argument(
            "--archive-rate",
            type=float,
            default=5.0,
            help="Max requests/sec to web.archive.org across all workers (0 = unlimited). Backblaze is never throttled.",
        )
        parser.add_argument("--asset", type=str, default=None, help="Process a single asset by its `url` field.")
        parser.add_argument("--dry-run", action="store_true", help="Compute but do not write to the database.")

    def handle(self, *args, **options):
        global _archive_limiter
        _archive_limiter = _RateLimiter(options["archive_rate"])

        assets = Asset.objects.filter(triangle_count=0)
        if options["asset"]:
            assets = assets.filter(url=options["asset"])
        assets = assets.order_by("pk")
        if options["limit"]:
            assets = assets[: options["limit"]]

        # Resolve each asset's ordered candidate formats up front (one DB pass).
        # No DB access happens in the worker threads.
        work = []  # (asset, [(format, url), ...])
        skipped_assets = 0
        for asset in assets.iterator():
            candidates = _candidates(asset)
            if candidates:
                work.append((asset, candidates))
            else:
                skipped_assets += 1

        self.stdout.write(
            f"{LOG_PREFIX} {len(work)} asset(s) to measure; {skipped_assets} have no measurable format. "
            f"archive.org capped at {options['archive_rate']}/s."
        )

        dry_run = options["dry_run"]
        updated_assets = 0
        unresolved_assets = 0
        failures = []

        with ThreadPoolExecutor(max_workers=options["workers"]) as pool:
            futures = {pool.submit(self._measure_asset, candidates): asset for asset, candidates in work}
            for future in as_completed(futures):
                asset = futures[future]
                fmt, count, errors = future.result()
                failures.extend((asset, f, msg) for f, msg in errors)

                if count is None:
                    unresolved_assets += 1
                    continue

                self.stdout.write(f"{LOG_PREFIX} {asset.url} {fmt.format_type} -> {count} triangles")
                if not dry_run:
                    Format.objects.filter(pk=fmt.pk).update(triangle_count=count)
                    # denorm_triangle_count queries the DB, so it sees the row we
                    # just updated; write only that field to skip the heavy custom
                    # save() (rank, search text, moderation logging, update_time).
                    asset.denorm_triangle_count()
                    Asset.objects.filter(pk=asset.pk).update(triangle_count=asset.triangle_count)
                updated_assets += 1

        if failures:
            self.stdout.write(f"{LOG_PREFIX} {len(failures)} format(s) failed to measure:")
            for asset, fmt, message in failures:
                self.stdout.write(f"{LOG_PREFIX}   {asset.url} {fmt.format_type}: {message}")

        verb = "Would update" if dry_run else "Updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"{LOG_PREFIX} {verb} {updated_assets} asset(s); "
                f"{unresolved_assets} still 0 (no format measurable)."
            )
        )

    @staticmethod
    def _measure_asset(candidates):
        """Try candidate formats in order; return the first measurable count.

        Returns ``(format, count, errors)`` where ``errors`` lists the formats
        that raised before a success (or all of them, if none succeeded).
        """
        errors = []
        for fmt, url in candidates:
            try:
                count = count_triangles(url, session=_session())
            except Exception as exc:
                # Broad on purpose: across 140k+ files we never want one
                # malformed model (bad struct, unexpected JSON, network error,
                # ...) to abort the backfill — record it and try the next format.
                errors.append((fmt, f"{type(exc).__name__}: {exc}"))
                continue
            if count is not None:
                return fmt, count, errors
        return None, None, errors
