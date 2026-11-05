"""Print the plan-estimate route's forward test and its gate, without writing anything.

The scoring lives in bidefy/models/plan_route.py, which every crawl runs and publishes to
models/metrics.json under "plan_route". This prints the same figures from the local archive:

    uv run python tools/plan_forward_test.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bidefy.crawler import store  # noqa: E402
from bidefy.models import plan_route  # noqa: E402


def report(data_root: Path, metrics_path: Path) -> dict:
    e = plan_route.evaluate(plan_route.pairs(store.load_all(data_root, plan_route.ENDPOINT),
                                             store.load_all(data_root, "contracts")))
    metrics = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.exists() else {}
    security_mape = (metrics.get("award_value_model") or {}).get("security_mape")
    active, reason = plan_route.gate(e, security_mape)
    return {**e, "would_serve": active, "gate": reason, "security_mape_to_beat": security_mape}


def main() -> None:
    print(json.dumps(report(ROOT / "data", ROOT / "models" / "metrics.json"), indent=2))


if __name__ == "__main__":
    main()
