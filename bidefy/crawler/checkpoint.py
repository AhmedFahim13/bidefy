"""Resume state for a crawl of one endpoint, stored as JSON in checkpoints/."""
from __future__ import annotations

import json
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

    @property
    def backfill_done(self) -> bool:
        return self.total_pages > 0 and self.next_page > self.total_pages

    def save(self, path: Path) -> None:
        self.updated_at = _now()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path, endpoint: str | None = None) -> "Checkpoint":
        if not path.exists():
            return cls(endpoint=endpoint or path.stem)
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(**data)
