"""Resume state for a crawl of one endpoint, stored as JSON in checkpoints/."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Checkpoint:
    endpoint: str
    next_page: int = 1
    total_pages: int = 0
    newest_id_seen: str = ""
    mode: str = "backfill"
    updated_at: str = field(default_factory=_now)
    last_run_pages: int = 0
    last_run_rows: int = 0
    last_run_status: str = ""
    backfill_completed: bool = False     # set once the archive has been walked end to end

    @property
    def backfill_done(self) -> bool:
        """Whether the whole archive has been crawled at least once.

        This used to be `next_page > total_pages` alone, which holds only until the index grows.
        New notices lengthen it every day, so a finished crawl looked unfinished again the next
        morning: the job dropped back into backfill and spent the night re-reading the oldest
        pages while the new notices on page one went unfetched. The fact is now remembered.
        """
        return self.backfill_completed or (self.total_pages > 0 and self.next_page > self.total_pages)

    def save(self, path: Path) -> None:
        self.updated_at = _now()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)

    @classmethod
    def load(cls, path: Path, endpoint: str | None = None) -> "Checkpoint":
        if not path.exists():
            return cls(endpoint=endpoint or path.stem)
        data = json.loads(path.read_text(encoding="utf-8"))
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        cp = cls(**known)
        if endpoint is not None and cp.endpoint != endpoint:
            raise ValueError(
                f"checkpoint at {path} is for endpoint {cp.endpoint!r}, not {endpoint!r}"
            )
        return cp
