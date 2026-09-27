"""One crawl per endpoint, enforced rather than remembered.

Two crawlers once ran against the same endpoint at the same time. Both read the same checkpoint,
both walked from the same page, both wrote rows, and both reported success; the only way to tell was
to measure the page rate and notice it had doubled. The workflow has carried a `concurrency` group
since, which stops two CI runs overlapping, but it cannot see a run started by hand on a laptop --
and that is exactly how it happened.

So the checkpoint gets a lock beside it. The file is created with O_EXCL, which is atomic on every
platform this runs on, so two processes racing to take it cannot both win. It records who holds it
and since when, because a lock that says nothing is worse than none: the first question is always
whether the holder is still alive.

A lock is taken over once it is older than a crawl could possibly be. A killed process leaves its
lock behind, and a pipeline that needs a human to delete a file before it can run again would fail
every night until somebody noticed. Six hours is longer than the longest budget the workflow sets.
"""
from __future__ import annotations

import contextlib
import json
import os
import socket
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

STALE_SECONDS = 6 * 3600


class CrawlLocked(RuntimeError):
    """Another crawl of this endpoint is already running."""


def _describe(path: Path) -> tuple[dict, float]:
    """What the lock says, and how many seconds ago it was written."""
    try:
        held = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        held = {}
    try:
        age = max(time.time() - path.stat().st_mtime, 0.0)
    except OSError:
        age = 0.0
    return held, age


@contextmanager
def held(checkpoint_path: Path, log=print, stale_seconds: float = STALE_SECONDS) -> Iterator[Path]:
    """Hold the lock for one endpoint's checkpoint, or refuse to run.

    Yields the lock's path. Releasing is unconditional: a crawl that raises must not leave the
    endpoint locked out until a human intervenes.
    """
    path = Path(checkpoint_path).with_suffix(".lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    mine = json.dumps({"host": socket.gethostname(), "pid": os.getpid(),
                       "since": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}) + "\n"
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        holder, age = _describe(path)
        if age < stale_seconds:
            raise CrawlLocked(
                f"{path.stem} is already being crawled by pid {holder.get('pid', '?')} on "
                f"{holder.get('host', '?')} since {holder.get('since', '?')} ({age / 60:.0f} minutes "
                f"ago). Two crawlers sharing one checkpoint both look successful and neither is. "
                f"Wait, or delete {path} if you know that run is gone."
            ) from None
        log(f"{path.stem}: taking over a lock {age / 3600:.1f} hours old from pid "
            f"{holder.get('pid', '?')} on {holder.get('host', '?')}; that run cannot still be alive")
        fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(mine)
        yield path
    finally:
        # A lock left behind goes stale on its own, so failing to remove it must never mask the
        # error that brought us here.
        with contextlib.suppress(OSError):
            path.unlink()
