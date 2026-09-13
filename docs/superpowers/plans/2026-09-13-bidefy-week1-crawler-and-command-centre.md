# Bidefy Week 1: Crawler, Index and Command Centre Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A checkpointed crawler that builds the full e-GP tender index into committed Parquet on a nightly GitHub Actions schedule, plus a self-updating command centre on GitHub Pages showing progress, next steps and Fahim's own task list.

**Architecture:** A small Python package `bidefy` with a `crawler` subpackage split into session (HTTP and rate limiting), parse (HTML to dicts), checkpoint (resume state), store (Parquet) and run (backfill and delta policy). Tests use saved HTML fixtures and a fake session, never the network. A `tools/build_site.py` script renders `status.yaml` and product docs into two static pages deployed by a Pages workflow.

**Tech Stack:** Python 3.12, uv, polars, pyarrow, pyyaml, markdown, pytest. GitHub Actions for crawl, CI and Pages. No paid services.

Spec: `docs/superpowers/specs/2026-09-13-bidefy-design.md`. Later plans cover contracts and entity resolution (week 2), the Worker site and push (weeks 3 and 4), and models (weeks 5 and 6).

---

## File structure

```
bidefy/                         Python package
  __init__.py
  crawler/
    __init__.py
    session.py                  EgpSession: cookie, POST endpoints, detail fetch, RateLimiter
    parse.py                    HTML row parser; parse_tender_rows, parse_contract_rows, parse_detail
    checkpoint.py               Checkpoint dataclass with JSON load/save
    store.py                    Parquet append, known_ids, load_all
    run.py                      crawl(): backfill and delta policy, failure policy, time budget, CLI
tools/
  capture_fixtures.py           Three real requests, saves tests/fixtures/*.html
  build_site.py                 status.yaml + docs -> site/index.html, site/doc.html
tests/
  fixtures/tenders_page.html    200-row TenderDetailsServlet response
  fixtures/contracts_page.html  200-row SearchNoaServlet response
  fixtures/detail_page.html     one ViewTender.jsp page
  test_parse.py
  test_checkpoint.py
  test_store.py
  test_session.py
  test_run.py
  test_build_site.py
docs/product/00-overview.md     first product doc section, rendered into doc.html
status.yaml                     command centre source of truth
checkpoints/                    tenders.json, contracts.json (committed by the crawl bot)
data/raw/tenders/*.parquet      committed by the crawl bot
.github/workflows/ci.yml        pytest on push
.github/workflows/crawl.yml     nightly crawl, commits data
.github/workflows/pages.yml     build and deploy the command centre
pyproject.toml
```

Conventions: LF line endings (enforced by `.gitattributes`), no em dashes in any text, commit after every task, `git pull` before every push.

---

### Task 1: Project scaffold, pytest and CI

**Files:**
- Create: `pyproject.toml`
- Create: `bidefy/__init__.py`
- Create: `bidefy/crawler/__init__.py`
- Create: `tests/test_smoke.py`
- Create: `.github/workflows/ci.yml`
- Modify: `.gitignore`

- [ ] **Step 1: Write pyproject.toml**

```toml
[project]
name = "bidefy"
version = "0.1.0"
description = "Tender intelligence for Bangladesh's e-GP procurement portal"
requires-python = ">=3.12"
dependencies = [
    "polars>=1.0",
    "pyarrow>=15",
    "pyyaml>=6",
    "markdown>=3.5",
]

[dependency-groups]
dev = ["pytest>=8"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["bidefy"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
```

- [ ] **Step 2: Create package files and a smoke test**

`bidefy/__init__.py`:
```python
"""Bidefy: tender intelligence for Bangladesh's e-GP portal."""

__version__ = "0.1.0"
```

`bidefy/crawler/__init__.py`:
```python
"""Crawler for the public pages of eprocure.gov.bd."""
```

`tests/test_smoke.py`:
```python
import bidefy


def test_version():
    assert bidefy.__version__ == "0.1.0"
```

- [ ] **Step 3: Replace .gitignore so data is committed**

```
__pycache__/
*.pyc
.venv/
.pytest_cache/
site/
review/*.tmp
```

- [ ] **Step 4: Install and run tests**

Run: `cd C:/Users/hp/Auto/egp-intel && uv sync && uv run pytest`
Expected: `1 passed`

- [ ] **Step 5: Write the CI workflow**

`.github/workflows/ci.yml`:
```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync
      - run: uv run pytest
```

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock bidefy tests .github/workflows/ci.yml .gitignore
git commit -m "Scaffold bidefy package, pytest and CI"
```

---

### Task 2: Capture HTML fixtures from the portal

Three real requests, the same count as the probe. Fixtures are committed so every later test runs offline.

**Files:**
- Create: `tools/capture_fixtures.py`
- Create: `tests/fixtures/tenders_page.html`
- Create: `tests/fixtures/contracts_page.html`
- Create: `tests/fixtures/detail_page.html`

- [ ] **Step 1: Write the capture script**

```python
"""Capture one page of each e-GP endpoint as test fixtures. Makes four requests."""
import http.cookiejar
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://www.eprocure.gov.bd"
UA = "Mozilla/5.0 bidefy-fixtures/0.1 (+https://github.com/AhmedFahim13/bidefy)"
OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def main() -> None:
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    opener.addheaders = [("User-Agent", UA), ("X-Requested-With", "XMLHttpRequest")]
    opener.open(BASE + "/resources/common/StdTenderSearch.jsp?h=t", timeout=60).read()

    def post(path: str, params: dict) -> str:
        data = urllib.parse.urlencode(params).encode()
        return opener.open(BASE + path, data=data, timeout=60).read().decode("utf-8", "ignore")

    tenders = post(
        "/TenderDetailsServlet",
        dict(funName="AllTenders", keyword="", pageNo=1, size=200, homeWSearch="homeWSearch", approve="false", h="t"),
    )
    contracts = post("/SearchNoaServlet", dict(keyword="", pageNo=1, size=200))
    first_id = re.search(r'name="id" value="(\d+)"', tenders)
    if not first_id:
        sys.exit("no tender id found in tenders page")
    detail = post("/resources/common/ViewTender.jsp", dict(id=first_id.group(1), h="t"))

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "tenders_page.html").write_text(tenders, encoding="utf-8")
    (OUT / "contracts_page.html").write_text(contracts, encoding="utf-8")
    (OUT / "detail_page.html").write_text(detail, encoding="utf-8")
    print("saved", len(tenders), len(contracts), len(detail), "bytes; detail id", first_id.group(1))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it**

Run: `uv run python tools/capture_fixtures.py`
Expected: `saved 2xxxxx 1xxxxx xxxxx bytes; detail id <number>` and three files under `tests/fixtures/`.

- [ ] **Step 3: Sanity check the fixtures**

Run: `grep -c "bgColor" tests/fixtures/tenders_page.html; grep -c "bgColor" tests/fixtures/contracts_page.html; grep -c "Procuring Entity Name" tests/fixtures/detail_page.html`
Expected: `200`, `200`, `1` (or more).

- [ ] **Step 4: Commit**

```bash
git add tools/capture_fixtures.py tests/fixtures
git commit -m "Add fixture capture script and e-GP HTML fixtures"
```

---

### Task 3: Row parser and parse_tender_rows

**Files:**
- Create: `bidefy/crawler/parse.py`
- Create: `tests/test_parse.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_parse.py`:
```python
from pathlib import Path

import pytest

from bidefy.crawler import parse

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def tenders_html() -> str:
    return (FIX / "tenders_page.html").read_text(encoding="utf-8")


def test_parse_tender_rows_count_and_total(tenders_html):
    rows, total_pages = parse.parse_tender_rows(tenders_html)
    assert len(rows) == 200
    assert total_pages > 3000


def test_parse_tender_row_fields(tenders_html):
    rows, _ = parse.parse_tender_rows(tenders_html)
    row = rows[0]
    assert set(row) == {
        "tender_id", "reference", "status", "nature", "title",
        "ministry", "organization", "procuring_entity",
        "procurement_type", "method", "published_at", "closing_at",
    }
    assert row["tender_id"].isdigit()
    assert row["status"] in {"Live", "Cancelled", "Closed", "Awarded", "Withdrawn", "Rejected", "Re-Tendered"} or row["status"]
    assert row["title"]
    assert row["published_at"].count("-") == 2 and "T" in row["published_at"]
    assert row["closing_at"] >= row["published_at"]


def test_tender_ids_unique(tenders_html):
    rows, _ = parse.parse_tender_rows(tenders_html)
    ids = [r["tender_id"] for r in rows]
    assert len(ids) == len(set(ids))


def test_parse_datetime():
    assert parse.parse_datetime("13-Sep-2026 11:00") == "2026-09-13T11:00"
    assert parse.parse_datetime("  28-Sep-2026 13:00,") == "2026-09-28T13:00"
    assert parse.parse_datetime("garbage") is None
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_parse.py -v`
Expected: FAIL with `ImportError` or `AttributeError: module 'bidefy.crawler.parse' has no attribute 'parse_tender_rows'`

- [ ] **Step 3: Write parse.py**

```python
"""Parse e-GP HTML fragments into plain dicts. No network, no dependencies."""
from __future__ import annotations

import re
from datetime import datetime
from html.parser import HTMLParser

_DATE_RE = re.compile(r"(\d{2}-[A-Za-z]{3}-\d{4} \d{2}:\d{2})")
_ID_MARK = "\x00id="


class _RowParser(HTMLParser):
    """Collects every <tr> as a list of cell strings. <br> and <p> become newlines.

    Hidden inputs with an id are collected in .hidden (for totalPages).
    A hidden input named "id" inside a cell is embedded as a marker so the
    tender id survives even if the visible text changes.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self.hidden: dict[str, str] = {}
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "tr":
            self._row = []
        elif tag == "td" and self._row is not None:
            self._cell = []
        elif tag in ("br", "p") and self._cell is not None:
            self._cell.append("\n")
        elif tag == "input" and a.get("type") == "hidden":
            if a.get("id"):
                self.hidden[a["id"]] = a.get("value", "")
            if a.get("name") == "id" and self._cell is not None:
                self._cell.append(f"{_ID_MARK}{a.get('value', '')}\x00")

    def handle_endtag(self, tag):
        if tag == "td" and self._cell is not None and self._row is not None:
            self._row.append("".join(self._cell))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def _parse(html: str) -> _RowParser:
    p = _RowParser()
    p.feed(html)
    return p


def _lines(cell: str) -> list[str]:
    """Split a cell on newlines, strip whitespace and trailing commas, drop empties and id markers."""
    out = []
    for line in cell.split("\n"):
        line = re.sub(r"\x00id=\d*\x00", "", line).strip().strip(",").strip()
        if line:
            out.append(line)
    return out


def _marker_id(cell: str) -> str | None:
    m = re.search(r"\x00id=(\d+)\x00", cell)
    return m.group(1) if m else None


def parse_datetime(text: str) -> str | None:
    """'13-Sep-2026 11:00' -> '2026-09-13T11:00'. Returns None if no date found."""
    m = _DATE_RE.search(text or "")
    if not m:
        return None
    return datetime.strptime(m.group(1), "%d-%b-%Y %H:%M").strftime("%Y-%m-%dT%H:%M")


def parse_tender_rows(html: str) -> tuple[list[dict], int]:
    """Rows from TenderDetailsServlet. Returns (rows, total_pages)."""
    p = _parse(html)
    rows = []
    for cells in p.rows:
        if len(cells) < 6 or not cells[0].strip().isdigit():
            continue
        c_id, c_title, c_org, c_type, c_dates = cells[1], cells[2], cells[3], cells[4], cells[5]
        id_lines = _lines(c_id)
        title_lines = _lines(c_title)
        org_lines = _lines(c_org)
        type_lines = _lines(c_type)
        dates = _DATE_RE.findall(c_dates)
        tender_id = _marker_id(c_title) or (id_lines[0] if id_lines else "")
        rows.append(
            {
                "tender_id": tender_id,
                "reference": id_lines[1] if len(id_lines) > 1 else "",
                "status": id_lines[-1] if len(id_lines) > 2 else "",
                "nature": title_lines[0] if title_lines else "",
                "title": " ".join(title_lines[1:]) if len(title_lines) > 1 else "",
                "ministry": org_lines[0] if org_lines else "",
                "organization": " / ".join(org_lines[1:-1]) if len(org_lines) > 2 else "",
                "procuring_entity": org_lines[-1] if len(org_lines) > 1 else "",
                "procurement_type": type_lines[0] if type_lines else "",
                "method": type_lines[-1] if len(type_lines) > 1 else "",
                "published_at": parse_datetime(dates[0]) if dates else None,
                "closing_at": parse_datetime(dates[1]) if len(dates) > 1 else None,
            }
        )
    total = int(p.hidden.get("totalPages", "0") or 0)
    return rows, total
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_parse.py -v`
Expected: 4 passed. If `test_parse_tender_row_fields` fails on a status value, print `rows[0]` and adjust only the assertion set, not the parser.

- [ ] **Step 5: Commit**

```bash
git add bidefy/crawler/parse.py tests/test_parse.py
git commit -m "Parse tender index rows from e-GP HTML"
```

---

### Task 4: parse_contract_rows

Contract rows have eight cells: serial, ministry and division, "id, ref / title / more / advertisement date", "procuring entity / method", district, contract signing date, awardee, value in crore BDT. The title cell contains both a truncated and a full copy of the title because of the page's read-more script, so the parser keeps the longest candidate line.

**Files:**
- Modify: `bidefy/crawler/parse.py`
- Modify: `tests/test_parse.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_parse.py`:
```python
@pytest.fixture(scope="module")
def contracts_html() -> str:
    return (FIX / "contracts_page.html").read_text(encoding="utf-8")


def test_parse_contract_rows_count_and_total(contracts_html):
    rows, total_pages = parse.parse_contract_rows(contracts_html)
    assert len(rows) == 200
    assert total_pages > 4000


def test_parse_contract_row_fields(contracts_html):
    rows, _ = parse.parse_contract_rows(contracts_html)
    row = rows[0]
    assert set(row) == {
        "tender_id", "reference", "title", "advertised_at", "ministry",
        "procuring_entity", "method", "district", "signed_on", "awardee", "value_crore",
    }
    assert row["tender_id"].isdigit()
    assert row["awardee"]
    assert isinstance(row["value_crore"], float)
    assert row["signed_on"] is None or len(row["signed_on"]) == 10
    assert "more" not in row["title"].split()


def test_contract_value_parse():
    assert parse.parse_value_crore("0.137") == 0.137
    assert parse.parse_value_crore("2,433.5") == 2433.5
    assert parse.parse_value_crore("abc") is None
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_parse.py -k contract -v`
Expected: FAIL with `AttributeError: ... has no attribute 'parse_contract_rows'`

- [ ] **Step 3: Add the contract parser to parse.py**

Append to `bidefy/crawler/parse.py`:
```python
_DAY_RE = re.compile(r"(\d{2}-[A-Za-z]{3}-\d{4})")


def parse_day(text: str) -> str | None:
    """'13-Sep-2026' -> '2026-09-13'. Returns None if no day found."""
    m = _DAY_RE.search(text or "")
    if not m:
        return None
    return datetime.strptime(m.group(1), "%d-%b-%Y").strftime("%Y-%m-%d")


def parse_value_crore(text: str) -> float | None:
    cleaned = re.sub(r"[^\d.]", "", text or "")
    if not cleaned or cleaned.count(".") > 1:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_contract_rows(html: str) -> tuple[list[dict], int]:
    """Rows from SearchNoaServlet. Returns (rows, total_pages)."""
    p = _parse(html)
    rows = []
    for cells in p.rows:
        if len(cells) < 8 or not cells[0].strip().isdigit():
            continue
        c_min, c_title, c_pe, c_dist, c_sign, c_award, c_val = cells[1], cells[2], cells[3], cells[4], cells[5], cells[6], cells[7]
        title_lines = _lines(c_title)
        head = title_lines[0] if title_lines else ""
        tender_id, _, reference = head.partition(",")
        middle = [l for l in title_lines[1:] if l.lower() not in ("more", "less", "...") and not _DATE_RE.search(l)]
        title = max(middle, key=len) if middle else ""
        pe_lines = _lines(c_pe)
        rows.append(
            {
                "tender_id": tender_id.strip(),
                "reference": reference.strip(),
                "title": title.replace("...", "").strip(),
                "advertised_at": parse_datetime(c_title),
                "ministry": " / ".join(_lines(c_min)),
                "procuring_entity": " ".join(pe_lines[:-1]) if len(pe_lines) > 1 else (pe_lines[0] if pe_lines else ""),
                "method": pe_lines[-1] if len(pe_lines) > 1 else "",
                "district": " ".join(_lines(c_dist)),
                "signed_on": parse_day(c_sign),
                "awardee": " ".join(_lines(c_award)),
                "value_crore": parse_value_crore(c_val),
            }
        )
    total = int(p.hidden.get("totalPages", "0") or 0)
    return rows, total
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_parse.py -v`
Expected: 7 passed. If the fixture's title cell layout differs from the description, print `parse._parse(contracts_html).rows[1]` and adjust the cell indices once; keep the tests.

- [ ] **Step 5: Commit**

```bash
git add bidefy/crawler/parse.py tests/test_parse.py
git commit -m "Parse contract award rows from e-GP HTML"
```

---

### Task 5: parse_detail

The detail page is label and value cells in rows. Lot rows have six cells with a numeric security amount in the fourth.

**Files:**
- Modify: `bidefy/crawler/parse.py`
- Modify: `tests/test_parse.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_parse.py`:
```python
@pytest.fixture(scope="module")
def detail_html() -> str:
    return (FIX / "detail_page.html").read_text(encoding="utf-8")


def test_parse_detail_fields(detail_html):
    d = parse.parse_detail(detail_html)
    assert d["tender_id"].isdigit()
    assert d["procuring_entity"]
    assert d["procuring_entity_district"]
    assert d["method"]
    assert isinstance(d["categories"], list) and d["categories"]
    assert d["security_bdt"] is None or d["security_bdt"] >= 0
    assert d["published_at"] and "T" in d["published_at"]
    assert isinstance(d["document_price_bdt"], (int, type(None)))


def test_parse_detail_empty():
    d = parse.parse_detail("<html><body>Session Expired</body></html>")
    assert d["tender_id"] == ""
    assert d["categories"] == []
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_parse.py -k detail -v`
Expected: FAIL with `AttributeError: ... 'parse_detail'`

- [ ] **Step 3: Add parse_detail**

Append to `bidefy/crawler/parse.py`:
```python
def _label_map(rows: list[list[str]]) -> dict[str, str]:
    """Pairs 'Label :' cells with the cell to their right, across all rows."""
    out: dict[str, str] = {}
    for cells in rows:
        for i in range(len(cells) - 1):
            label = cells[i].strip()
            if label.endswith(":"):
                key = label.rstrip(":").strip()
                value = " ".join(_lines(cells[i + 1]))
                if key and key not in out:
                    out[key] = value
    return out


def _to_int(text: str | None) -> int | None:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else None


def parse_detail(html: str) -> dict:
    """Fields from ViewTender.jsp. Missing fields are '' or None; categories is a list."""
    p = _parse(html)
    m = _label_map(p.rows)
    security = None
    for cells in p.rows:
        if len(cells) == 6 and cells[0].strip().isdigit():
            amount = _to_int(cells[3])
            if amount is not None:
                security = (security or 0) + amount
    categories = [c.strip() for c in m.get("Category", "").split(";") if c.strip()]
    return {
        "tender_id": re.sub(r"\D", "", m.get("Tender/Proposal ID", "")),
        "reference": m.get("Invitation Reference No.", ""),
        "ministry": m.get("Ministry", ""),
        "division": m.get("Division", ""),
        "organization": m.get("Organization", ""),
        "procuring_entity": m.get("Procuring Entity Name", ""),
        "procuring_entity_district": m.get("Procuring Entity District", ""),
        "nature": m.get("Procurement Nature", ""),
        "procurement_type": m.get("Procurement Type", ""),
        "method": m.get("Procurement Method", ""),
        "budget_type": m.get("Budget Type", ""),
        "source_of_funds": m.get("Source of Funds", ""),
        "package": m.get("Tender/Proposal Package No. and Description", ""),
        "categories": categories,
        "published_at": parse_datetime(m.get("Date and Time", "")),
        "closing_at": parse_datetime(m.get("Tender/Proposal Closing Date and Time", "") or m.get("Date and Time", "")),
        "document_price_bdt": _to_int(m.get("Tender/Proposal Document Price (In BDT)")),
        "security_bdt": security,
        "brief": m.get("Brief Description of Goods and Related Service", "") or m.get("Brief Description of Works", "") or m.get("Brief Description of Services", ""),
    }
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_parse.py -v`
Expected: 9 passed. The closing date label on the page is split across cells ("Tender/Proposal Closing" then "Date and Time :"); if `closing_at` equals `published_at`, print `parse._label_map(parse._parse(detail_html).rows)` and map the correct key once.

- [ ] **Step 5: Commit**

```bash
git add bidefy/crawler/parse.py tests/test_parse.py
git commit -m "Parse tender detail pages"
```

---

### Task 6: Checkpoint

**Files:**
- Create: `bidefy/crawler/checkpoint.py`
- Create: `tests/test_checkpoint.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_checkpoint.py`:
```python
from bidefy.crawler.checkpoint import Checkpoint


def test_roundtrip(tmp_path):
    path = tmp_path / "tenders.json"
    cp = Checkpoint(endpoint="tenders", next_page=42, total_pages=3129, newest_id_seen="1332746", mode="backfill")
    cp.save(path)
    loaded = Checkpoint.load(path)
    assert loaded == cp
    assert loaded.updated_at


def test_load_missing_returns_fresh(tmp_path):
    cp = Checkpoint.load(tmp_path / "nope.json", endpoint="contracts")
    assert cp.endpoint == "contracts"
    assert cp.next_page == 1
    assert cp.total_pages == 0
    assert cp.newest_id_seen == ""


def test_backfill_done():
    assert Checkpoint(endpoint="t", next_page=10, total_pages=9).backfill_done
    assert not Checkpoint(endpoint="t", next_page=1, total_pages=0).backfill_done
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_checkpoint.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bidefy.crawler.checkpoint'`

- [ ] **Step 3: Write checkpoint.py**

```python
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
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_checkpoint.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add bidefy/crawler/checkpoint.py tests/test_checkpoint.py
git commit -m "Add crawl checkpoint"
```

---

### Task 7: Parquet store

**Files:**
- Create: `bidefy/crawler/store.py`
- Create: `tests/test_store.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_store.py`:
```python
import polars as pl

from bidefy.crawler import store


def _rows(*ids):
    return [
        {"tender_id": i, "reference": "r", "status": "Live", "nature": "Goods", "title": f"t{i}",
         "ministry": "m", "organization": "", "procuring_entity": "pe", "procurement_type": "NCT",
         "method": "OTM", "published_at": "2026-09-13T11:00", "closing_at": "2026-09-28T13:00"}
        for i in ids
    ]


def test_append_and_known_ids(tmp_path):
    path = store.append_rows(_rows("1", "2"), tmp_path, "tenders")
    assert path.exists() and path.suffix == ".parquet"
    assert store.known_ids(tmp_path, "tenders") == {"1", "2"}
    assert store.known_ids(tmp_path, "contracts") == set()


def test_append_empty_writes_nothing(tmp_path):
    assert store.append_rows([], tmp_path, "tenders") is None
    assert store.known_ids(tmp_path, "tenders") == set()


def test_load_all_keeps_latest_by_id(tmp_path):
    store.append_rows(_rows("1"), tmp_path, "tenders")
    later = _rows("1")
    later[0]["status"] = "Cancelled"
    store.append_rows(later, tmp_path, "tenders")
    df = store.load_all(tmp_path, "tenders")
    assert isinstance(df, pl.DataFrame)
    assert df.height == 1
    assert df["status"][0] == "Cancelled"
    assert "fetched_at" in df.columns
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_store.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write store.py**

```python
"""Append-only Parquet store under data/raw/<endpoint>/. Dedupe happens on read."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import polars as pl

ID_COLUMN = "tender_id"


def _dir(root: Path, endpoint: str) -> Path:
    return Path(root) / "raw" / endpoint


def append_rows(rows: list[dict], root: Path, endpoint: str) -> Path | None:
    """Write rows to a new part file. Returns the path, or None if rows is empty."""
    if not rows:
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    df = pl.DataFrame(rows).with_columns(pl.lit(stamp).alias("fetched_at"))
    out = _dir(root, endpoint)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"part-{stamp}.parquet"
    df.write_parquet(path, compression="zstd")
    return path


def _parts(root: Path, endpoint: str) -> list[Path]:
    d = _dir(root, endpoint)
    return sorted(d.glob("part-*.parquet")) if d.exists() else []


def known_ids(root: Path, endpoint: str) -> set[str]:
    parts = _parts(root, endpoint)
    if not parts:
        return set()
    ids = pl.concat([pl.read_parquet(p, columns=[ID_COLUMN]) for p in parts])
    return set(ids[ID_COLUMN].cast(pl.Utf8).to_list())


def load_all(root: Path, endpoint: str) -> pl.DataFrame:
    """All rows, one per id, keeping the most recently fetched copy."""
    parts = _parts(root, endpoint)
    if not parts:
        return pl.DataFrame()
    df = pl.concat([pl.read_parquet(p) for p in parts], how="diagonal_relaxed")
    return df.sort("fetched_at").unique(subset=[ID_COLUMN], keep="last").sort(ID_COLUMN)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_store.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add bidefy/crawler/store.py tests/test_store.py
git commit -m "Add append-only Parquet store"
```

---

### Task 8: Session and rate limiter

The session owns the cookie and the two POST shapes. Transport is injectable so tests never touch the network.

**Files:**
- Create: `bidefy/crawler/session.py`
- Create: `tests/test_session.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_session.py`:
```python
from bidefy.crawler.session import EgpSession, RateLimiter, SessionExpired


class Clock:
    def __init__(self):
        self.t = 1000.0
        self.slept = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


def test_rate_limiter_spaces_calls():
    clock = Clock()
    rl = RateLimiter(min_interval=1.0, now=clock.now, sleep=clock.sleep)
    rl.wait()          # first call: no sleep
    clock.t += 0.3
    rl.wait()          # 0.7 left
    assert clock.slept == [0.7]
    clock.t += 2.0
    rl.wait()          # long gap: no sleep
    assert clock.slept == [0.7]


def _transport(log):
    def send(method, url, data, headers):
        log.append((method, url, data))
        if url.endswith("StdTenderSearch.jsp?h=t"):
            return 200, "<html>shell</html>"
        if url.endswith("/TenderDetailsServlet"):
            return 200, "<tr class='bgColor-white'><td>1</td></tr>"
        if url.endswith("/SearchNoaServlet"):
            return 200, "<tr class='bgColor-white'><td>1</td></tr>"
        if url.endswith("/ViewTender.jsp"):
            return 200, "<html>detail</html>"
        return 404, ""
    return send


def test_list_page_posts_expected_params():
    log = []
    s = EgpSession(transport=_transport(log), min_interval=0)
    body = s.list_page("tenders", page=3, size=200)
    assert "bgColor" in body
    assert log[0][0] == "GET"                       # session warm-up first
    method, url, data = log[1]
    assert method == "POST" and url.endswith("/TenderDetailsServlet")
    assert data["funName"] == "AllTenders" and data["pageNo"] == "3" and data["size"] == "200"
    s.list_page("contracts", page=1)
    assert log[2][1].endswith("/SearchNoaServlet") and log[2][2] == {"keyword": "", "pageNo": "1", "size": "200"}


def test_detail_posts_id():
    log = []
    s = EgpSession(transport=_transport(log), min_interval=0)
    assert "detail" in s.detail("1329525")
    assert log[-1][2] == {"id": "1329525", "h": "t"}


def test_session_expired_raises():
    def send(method, url, data, headers):
        return 200, "<title>Session Expired</title> Your session has been expired"
    s = EgpSession(transport=send, min_interval=0)
    try:
        s.list_page("tenders", page=1)
        assert False, "expected SessionExpired"
    except SessionExpired:
        pass
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_session.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write session.py**

```python
"""HTTP session against eprocure.gov.bd with a cookie, a rate limiter and an injectable transport."""
from __future__ import annotations

import http.cookiejar
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

BASE = "https://www.eprocure.gov.bd"
UA = "Mozilla/5.0 bidefy-crawler/0.1 (+https://github.com/AhmedFahim13/bidefy; polite, 1 req/s)"
WARMUP_PATH = "/resources/common/StdTenderSearch.jsp?h=t"
ENDPOINTS = {
    "tenders": ("/TenderDetailsServlet", lambda page, size: {
        "funName": "AllTenders", "keyword": "", "pageNo": str(page), "size": str(size),
        "homeWSearch": "homeWSearch", "approve": "false", "h": "t"}),
    "contracts": ("/SearchNoaServlet", lambda page, size: {
        "keyword": "", "pageNo": str(page), "size": str(size)}),
}
DETAIL_PATH = "/resources/common/ViewTender.jsp"

Transport = Callable[[str, str, dict | None, dict], tuple[int, str]]


class SessionExpired(RuntimeError):
    pass


class HttpFailure(RuntimeError):
    pass


class RateLimiter:
    def __init__(self, min_interval: float = 1.0, now=time.monotonic, sleep=time.sleep) -> None:
        self.min_interval = min_interval
        self._now = now
        self._sleep = sleep
        self._last: float | None = None

    def wait(self) -> None:
        if self._last is not None:
            remaining = self.min_interval - (self._now() - self._last)
            if remaining > 0:
                self._sleep(round(remaining, 6))
        self._last = self._now()


def urllib_transport(timeout: float = 60.0) -> Transport:
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    def send(method: str, url: str, data: dict | None, headers: dict) -> tuple[int, str]:
        body = urllib.parse.urlencode(data).encode() if data is not None else None
        req = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with opener.open(req, timeout=timeout) as resp:
                return resp.status, resp.read().decode("utf-8", "ignore")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "ignore")
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise HttpFailure(str(e)) from e

    return send


class EgpSession:
    def __init__(self, transport: Transport | None = None, min_interval: float = 1.0) -> None:
        self._send = transport or urllib_transport()
        self._limiter = RateLimiter(min_interval)
        self._warm = False
        self._headers = {"User-Agent": UA, "X-Requested-With": "XMLHttpRequest"}

    def _request(self, method: str, path: str, data: dict | None = None) -> str:
        self._limiter.wait()
        status, body = self._send(method, BASE + path, data, self._headers)
        if status != 200:
            raise HttpFailure(f"{method} {path} -> HTTP {status}")
        if "session has been expired" in body or "<title>Session Expired</title>" in body:
            self._warm = False
            raise SessionExpired(path)
        return body

    def warm_up(self) -> None:
        self._request("GET", WARMUP_PATH)
        self._warm = True

    def list_page(self, endpoint: str, page: int, size: int = 200) -> str:
        if not self._warm:
            self.warm_up()
        path, params = ENDPOINTS[endpoint]
        return self._request("POST", path, params(page, size))

    def detail(self, tender_id: str) -> str:
        if not self._warm:
            self.warm_up()
        return self._request("POST", DETAIL_PATH, {"id": str(tender_id), "h": "t"})
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_session.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add bidefy/crawler/session.py tests/test_session.py
git commit -m "Add e-GP session with rate limiter and injectable transport"
```

---

### Task 9: Crawl policy (backfill, delta, failures, time budget)

**Files:**
- Create: `bidefy/crawler/run.py`
- Create: `tests/test_run.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_run.py`:
```python
import re
from pathlib import Path

import pytest

from bidefy.crawler import run, store
from bidefy.crawler.checkpoint import Checkpoint
from bidefy.crawler.session import HttpFailure

FIX = Path(__file__).parent / "fixtures"
PAGE = (FIX / "tenders_page.html").read_text(encoding="utf-8")


class FakeSession:
    """Serves the fixture for every page; fails when told to."""

    def __init__(self, fail_times=0, total_pages_override=None):
        self.calls = []
        self.fail_times = fail_times
        self.html = PAGE
        if total_pages_override is not None:
            self.html = re.sub(r'id="totalPages" value="\d+"', f'id="totalPages" value="{total_pages_override}"', PAGE)

    def list_page(self, endpoint, page, size=200):
        self.calls.append(page)
        if self.fail_times > 0:
            self.fail_times -= 1
            raise HttpFailure("boom")
        return self.html


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        self.t += 10.0      # each check advances ten seconds
        return self.t


def _cp(tmp_path, **kw):
    return tmp_path / "checkpoints" / "tenders.json"


def test_backfill_advances_checkpoint_and_stores_rows(tmp_path):
    session = FakeSession(total_pages_override=3)
    summary = run.crawl(session, "tenders", "backfill", tmp_path / "data", _cp(tmp_path), time_budget_s=10_000)
    assert session.calls == [1, 2, 3]
    cp = Checkpoint.load(_cp(tmp_path))
    assert cp.next_page == 4 and cp.total_pages == 3 and cp.backfill_done
    assert summary.pages == 3 and summary.rows == 600 and summary.status == "done"
    assert len(store.known_ids(tmp_path / "data", "tenders")) == 200   # same ids every page, deduped on read


def test_backfill_resumes_from_checkpoint(tmp_path):
    Checkpoint(endpoint="tenders", next_page=2, total_pages=3).save(_cp(tmp_path))
    session = FakeSession(total_pages_override=3)
    run.crawl(session, "tenders", "backfill", tmp_path / "data", _cp(tmp_path), time_budget_s=10_000)
    assert session.calls == [2, 3]


def test_backfill_stops_on_time_budget(tmp_path):
    session = FakeSession(total_pages_override=50)
    summary = run.crawl(session, "tenders", "backfill", tmp_path / "data", _cp(tmp_path), time_budget_s=25, now=FakeClock())
    assert summary.status == "budget"
    assert 1 <= len(session.calls) <= 3
    assert Checkpoint.load(_cp(tmp_path)).next_page == len(session.calls) + 1


def test_three_consecutive_failures_abort_without_moving_checkpoint(tmp_path):
    session = FakeSession(fail_times=3, total_pages_override=5)
    summary = run.crawl(session, "tenders", "backfill", tmp_path / "data", _cp(tmp_path), time_budget_s=10_000)
    assert summary.status == "aborted"
    assert Checkpoint.load(_cp(tmp_path)).next_page == 1


def test_two_failures_then_success_continues(tmp_path):
    session = FakeSession(fail_times=2, total_pages_override=1)
    summary = run.crawl(session, "tenders", "backfill", tmp_path / "data", _cp(tmp_path), time_budget_s=10_000)
    assert summary.status == "done" and summary.pages == 1


def test_delta_stops_when_page_has_no_new_ids(tmp_path):
    session = FakeSession(total_pages_override=3)
    run.crawl(session, "tenders", "backfill", tmp_path / "data", _cp(tmp_path), time_budget_s=10_000)
    session.calls.clear()
    summary = run.crawl(session, "tenders", "delta", tmp_path / "data", _cp(tmp_path), time_budget_s=10_000)
    assert session.calls == [1]
    assert summary.rows == 0 and summary.status == "done"
    cp = Checkpoint.load(_cp(tmp_path))
    assert cp.mode == "delta" and cp.next_page == 4    # backfill position untouched


def test_delta_on_empty_store_stores_first_page(tmp_path):
    session = FakeSession(total_pages_override=1)
    summary = run.crawl(session, "tenders", "delta", tmp_path / "data", _cp(tmp_path), time_budget_s=10_000)
    assert summary.rows == 200
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_run.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write run.py**

```python
"""Crawl policy: backfill walks pages from the checkpoint; delta walks newest-first until nothing is new."""
from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import parse, store
from .checkpoint import Checkpoint
from .session import EgpSession, HttpFailure, SessionExpired

MAX_CONSECUTIVE_FAILURES = 3
PAGE_SIZE = 200
PARSERS: dict[str, Callable[[str], tuple[list[dict], int]]] = {
    "tenders": parse.parse_tender_rows,
    "contracts": parse.parse_contract_rows,
}


@dataclass
class Summary:
    endpoint: str
    mode: str
    pages: int = 0
    rows: int = 0
    status: str = "running"     # done | budget | aborted


def _fetch(session, endpoint: str, page: int, parser, log) -> tuple[list[dict], int] | None:
    """One page with the failure policy applied by the caller. Returns None on failure."""
    try:
        html = session.list_page(endpoint, page, PAGE_SIZE)
    except (HttpFailure, SessionExpired) as e:
        log(f"page {page}: {type(e).__name__}: {e}")
        return None
    rows, total = parser(html)
    if not rows:
        log(f"page {page}: zero rows")
        return None
    return rows, total


def crawl(
    session: EgpSession,
    endpoint: str,
    mode: str,
    data_root: Path,
    checkpoint_path: Path,
    time_budget_s: float,
    now: Callable[[], float] = time.monotonic,
    log: Callable[[str], None] = print,
) -> Summary:
    parser = PARSERS[endpoint]
    cp = Checkpoint.load(checkpoint_path, endpoint=endpoint)
    summary = Summary(endpoint=endpoint, mode=mode)
    started = now()
    failures = 0

    if mode == "backfill":
        page = cp.next_page
        while True:
            if cp.total_pages and page > cp.total_pages:
                summary.status = "done"
                break
            if now() - started > time_budget_s:
                summary.status = "budget"
                break
            got = _fetch(session, endpoint, page, parser, log)
            if got is None:
                failures += 1
                if failures >= MAX_CONSECUTIVE_FAILURES:
                    summary.status = "aborted"
                    break
                continue
            failures = 0
            rows, total = got
            store.append_rows(rows, data_root, endpoint)
            summary.pages += 1
            summary.rows += len(rows)
            cp.total_pages = total or cp.total_pages
            cp.next_page = page + 1
            cp.mode = "backfill"
            cp.save(checkpoint_path)
            page += 1

    elif mode == "delta":
        known = store.known_ids(data_root, endpoint)
        page = 1
        newest = cp.newest_id_seen
        while True:
            if now() - started > time_budget_s:
                summary.status = "budget"
                break
            got = _fetch(session, endpoint, page, parser, log)
            if got is None:
                failures += 1
                if failures >= MAX_CONSECUTIVE_FAILURES:
                    summary.status = "aborted"
                    break
                continue
            failures = 0
            rows, total = got
            new_rows = [r for r in rows if r["tender_id"] not in known]
            summary.pages += 1
            if new_rows:
                store.append_rows(new_rows, data_root, endpoint)
                summary.rows += len(new_rows)
                known.update(r["tender_id"] for r in new_rows)
                newest = max([newest] + [r["tender_id"] for r in new_rows], key=lambda s: int(s or 0))
            if len(new_rows) < len(rows) or (total and page >= total):
                summary.status = "done"
                break
            page += 1
        cp.mode = "delta"
        cp.newest_id_seen = newest
        cp.save(checkpoint_path)
    else:
        raise ValueError(f"unknown mode {mode}")

    cp.last_run_pages, cp.last_run_rows, cp.last_run_status = summary.pages, summary.rows, summary.status
    cp.save(checkpoint_path)
    log(f"{endpoint} {mode}: {summary.status}, {summary.pages} pages, {summary.rows} rows")
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Crawl the e-GP public index")
    ap.add_argument("--endpoint", choices=list(PARSERS), required=True)
    ap.add_argument("--mode", choices=["backfill", "delta"], required=True)
    ap.add_argument("--budget-min", type=float, default=300)
    ap.add_argument("--data-root", default="data")
    ap.add_argument("--checkpoints", default="checkpoints")
    ap.add_argument("--interval", type=float, default=1.0, help="seconds between requests")
    a = ap.parse_args(argv)
    session = EgpSession(min_interval=a.interval)
    summary = crawl(
        session, a.endpoint, a.mode, Path(a.data_root), Path(a.checkpoints) / f"{a.endpoint}.json",
        time_budget_s=a.budget_min * 60,
    )
    return 0 if summary.status in ("done", "budget") else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_run.py -v`
Expected: 7 passed. Note on the delta stop rule: a page where every id is already known, or where any id is known, ends the walk. The fixture has the same 200 ids on every page, so the second delta call stops at page one with zero new rows.

- [ ] **Step 5: Commit**

```bash
git add bidefy/crawler/run.py tests/test_run.py
git commit -m "Add crawl policy with checkpointed backfill and delta"
```

---

### Task 10: Nightly crawl workflow and first real run

The workflow commits data and checkpoints as a bot. Because a runner can be slow, backfill runs in five-hour chunks across nights. Dispatch one chunk locally first so the first data lands today.

**Files:**
- Create: `.github/workflows/crawl.yml`
- Modify: `README.md`

- [ ] **Step 1: Write the workflow**

`.github/workflows/crawl.yml`:
```yaml
name: Crawl e-GP

on:
  schedule:
    - cron: "0 20 * * *"        # 02:00 Dhaka
  workflow_dispatch:
    inputs:
      endpoint:
        description: tenders or contracts
        default: tenders
      mode:
        description: backfill or delta
        default: backfill
      budget_min:
        description: minutes before the run checkpoints and exits
        default: "300"

concurrency:
  group: crawl
  cancel-in-progress: false

permissions:
  contents: write

jobs:
  crawl:
    runs-on: ubuntu-latest
    timeout-minutes: 350
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync
      - name: Decide mode for scheduled runs
        id: mode
        run: |
          EP="${{ github.event.inputs.endpoint || 'tenders' }}"
          MODE="${{ github.event.inputs.mode || '' }}"
          if [ -z "$MODE" ]; then
            if [ -f "checkpoints/$EP.json" ] && python -c "import json,sys;c=json.load(open('checkpoints/$EP.json'));sys.exit(0 if c['total_pages'] and c['next_page']>c['total_pages'] else 1)"; then
              MODE=delta
            else
              MODE=backfill
            fi
          fi
          echo "endpoint=$EP" >> "$GITHUB_OUTPUT"
          echo "mode=$MODE" >> "$GITHUB_OUTPUT"
      - name: Crawl
        run: uv run python -m bidefy.crawler.run --endpoint "${{ steps.mode.outputs.endpoint }}" --mode "${{ steps.mode.outputs.mode }}" --budget-min "${{ github.event.inputs.budget_min || '300' }}"
      - name: Commit data
        run: |
          git config user.name "bidefy-bot"
          git config user.email "bidefy-bot@users.noreply.github.com"
          git add data checkpoints
          if git diff --cached --quiet; then echo "nothing to commit"; exit 0; fi
          git commit -m "data: ${{ steps.mode.outputs.endpoint }} ${{ steps.mode.outputs.mode }} $(date -u +%Y-%m-%dT%H:%MZ)"
          git pull --rebase
          git push
```

- [ ] **Step 2: Run a short local backfill to prove the CLI end to end**

Run: `uv run python -m bidefy.crawler.run --endpoint tenders --mode backfill --budget-min 2`
Expected: about 100 pages in two minutes from Dhaka, output ending `tenders backfill: budget, N pages, N*200 rows`, files under `data/raw/tenders/` and `checkpoints/tenders.json` with `next_page` = N+1.

- [ ] **Step 3: Commit code and the first data, then push**

```bash
git add .github/workflows/crawl.yml data checkpoints
git commit -m "Add nightly crawl workflow and first tender pages"
git pull --rebase
git push
```

- [ ] **Step 4: Dispatch a full-budget run on Actions and confirm it resumes from the checkpoint**

Run: `gh workflow run "Crawl e-GP" -f endpoint=tenders -f mode=backfill -f budget_min=300 && sleep 90 && gh run list --workflow "Crawl e-GP" --limit 1`
Expected: a run in progress. After it finishes (up to five hours), `gh run view --log <id> | grep "tenders backfill"` shows `budget` or `done`, and a bot commit on main advances `checkpoints/tenders.json`. Then `git pull` locally.

- [ ] **Step 5: Update the README**

Replace `README.md` with:
```markdown
# Bidefy

Tender intelligence for Bangladesh's public e-GP procurement portal.

- Design spec: `docs/superpowers/specs/2026-09-13-bidefy-design.md`
- Command centre: published by the Pages workflow (link added once live)

## Crawler

```bash
uv sync
uv run pytest
uv run python -m bidefy.crawler.run --endpoint tenders --mode backfill --budget-min 60
uv run python -m bidefy.crawler.run --endpoint tenders --mode delta
```

Runs nightly on GitHub Actions at one request per second, checkpointed in `checkpoints/`,
data committed under `data/raw/`. Backfill resumes across nights until `next_page` passes
`total_pages`; scheduled runs then switch to delta automatically.
```

- [ ] **Step 6: Commit**

```bash
git add README.md
git commit -m "Document crawler usage"
git pull --rebase
git push
```

---

### Task 11: status.yaml and progress computation

**Files:**
- Create: `status.yaml`
- Create: `tools/build_site.py`
- Create: `tests/test_build_site.py`

- [ ] **Step 1: Write status.yaml**

```yaml
project: Bidefy
tagline: Tender intelligence for Bangladesh's e-GP portal
launch_target: 2026-10-11
phases:
  - id: w1
    name: "Week 1: crawler and index"
    tasks:
      - {id: w1-scaffold, title: "Package scaffold, pytest, CI", owner: claude, state: done, weight: 1}
      - {id: w1-fixtures, title: "HTML fixtures from the portal", owner: claude, state: done, weight: 1}
      - {id: w1-parse, title: "Parsers for tender, contract and detail pages", owner: claude, state: done, weight: 3}
      - {id: w1-checkpoint, title: "Checkpoint and Parquet store", owner: claude, state: done, weight: 2}
      - {id: w1-session, title: "Session, rate limiter, crawl policy", owner: claude, state: done, weight: 3}
      - {id: w1-workflow, title: "Nightly crawl workflow", owner: claude, state: done, weight: 2}
      - {id: w1-backfill, title: "Full tender index backfilled", owner: claude, state: doing, weight: 3, note: "Runs across nights; see checkpoint"}
      - {id: w1-centre, title: "Command centre on GitHub Pages", owner: claude, state: doing, weight: 2}
      - {id: w1-cloudflare, title: "Create Cloudflare account and run wrangler login", owner: fahim, state: todo, weight: 1, note: "Needed before week 2 D1 work"}
      - {id: w1-terms, title: "Read e-GP terms and disclaimer pages once", owner: fahim, state: todo, weight: 1, note: "eprocure.gov.bd/TermsNConditions.jsp and /PrivacyPolicy.jsp"}
  - id: w2
    name: "Week 2: contracts, entity resolution, D1, Worker skeleton"
    tasks:
      - {id: w2-contracts, title: "Contracts index backfilled", owner: claude, state: todo, weight: 3}
      - {id: w2-resolve, title: "Entity resolution with review queue", owner: claude, state: todo, weight: 4}
      - {id: w2-d1, title: "D1 schema and nightly load within write limits", owner: claude, state: todo, weight: 3}
      - {id: w2-worker, title: "Worker skeleton with Hono", owner: claude, state: todo, weight: 2}
      - {id: w2-review, title: "Review review/pairs.csv when asked", owner: fahim, state: todo, weight: 1}
      - {id: w2-domain, title: "Decide domain or workers.dev", owner: fahim, state: todo, weight: 1, note: "About 1,200 taka a year if bought"}
  - id: w3
    name: "Week 3: site pages, PWA, push"
    tasks:
      - {id: w3-pages, title: "Live tenders, tender, alerts pages", owner: claude, state: todo, weight: 4}
      - {id: w3-pwa, title: "PWA manifest, service worker, push subscriptions", owner: claude, state: todo, weight: 3}
  - id: w4
    name: "Week 4: classifier, alert cron, public launch"
    tasks:
      - {id: w4-classifier, title: "Category classifier with metrics and deferral", owner: claude, state: todo, weight: 3}
      - {id: w4-cron, title: "Hourly alert matcher and push sender", owner: claude, state: todo, weight: 3}
      - {id: w4-launch, title: "Public launch v0.1", owner: claude, state: todo, weight: 2}
      - {id: w4-post, title: "Write and publish the launch post", owner: fahim, state: todo, weight: 1}
  - id: w5
    name: "Week 5: award-value model"
    tasks:
      - {id: w5-model, title: "LightGBM award model with interval and baseline", owner: claude, state: todo, weight: 4}
      - {id: w5-price, title: "Talk to five bidders about the Pro price", owner: fahim, state: todo, weight: 2}
  - id: w6
    name: "Week 6: anomaly flags and profiles"
    tasks:
      - {id: w6-flags, title: "Winner concentration and residual flags", owner: claude, state: todo, weight: 3}
      - {id: w6-profiles, title: "Bidder and procuring entity profile pages", owner: claude, state: todo, weight: 3}
  - id: w7
    name: "Week 7: product document, pricing, polish"
    tasks:
      - {id: w7-doc, title: "Full product document in the Auto structure", owner: claude, state: todo, weight: 3}
      - {id: w7-pricing, title: "Pricing page with request-access form", owner: claude, state: todo, weight: 2}
      - {id: w7-polish, title: "Polish, stale banner, dashboard final", owner: claude, state: todo, weight: 2}
  - id: w8
    name: "Week 8: usage, demo, outreach"
    tasks:
      - {id: w8-usage, title: "Usage numbers collected and shown", owner: claude, state: todo, weight: 2}
      - {id: w8-demo, title: "Record two-minute demo video", owner: fahim, state: todo, weight: 2}
      - {id: w8-outreach, title: "Message the four Advanced AI Lab product managers", owner: fahim, state: todo, weight: 3}
      - {id: w8-bkash, title: "bKash merchant account for the Pro tier (later)", owner: fahim, state: todo, weight: 1}
```

- [ ] **Step 2: Write the failing tests**

`tests/test_build_site.py`:
```python
from tools import build_site

STATUS = {
    "project": "Bidefy",
    "tagline": "t",
    "launch_target": "2026-10-11",
    "phases": [
        {"id": "w1", "name": "Week 1", "tasks": [
            {"id": "a", "title": "Done thing", "owner": "claude", "state": "done", "weight": 3},
            {"id": "b", "title": "Doing thing", "owner": "claude", "state": "doing", "weight": 1},
            {"id": "c", "title": "Your thing", "owner": "fahim", "state": "todo", "weight": 1, "note": "n"},
        ]},
        {"id": "w2", "name": "Week 2", "tasks": [
            {"id": "d", "title": "Later thing", "owner": "claude", "state": "todo", "weight": 5},
        ]},
    ],
}


def test_compute_progress():
    p = build_site.compute_progress(STATUS)
    assert p["percent"] == 30            # 3 of 10 weight
    assert p["done_count"] == 1 and p["total_count"] == 4
    assert [t["id"] for t in p["next_steps"]] == ["b", "c", "d"]
    assert [t["id"] for t in p["fahim_tasks"]] == ["c"]
    assert [t["title"] for t in p["done"]] == ["Done thing"]
    assert p["phases"][0]["percent"] == 60


def test_render_dashboard_contains_key_numbers():
    p = build_site.compute_progress(STATUS)
    html = build_site.render_dashboard(STATUS, p, crawl={"tenders": {"next_page": 5, "total_pages": 10, "updated_at": "2026-09-13T00:00:00Z", "last_run_status": "budget"}}, metrics=None)
    assert "30%" in html and "Your thing" in html and "Later thing" in html
    assert "tenders" in html and "5" in html
    assert "<title>Bidefy" in html


def test_render_doc_builds_toc():
    html = build_site.render_doc(STATUS, [("Overview", "<p>Hello</p>"), ("Market", "<p>World</p>")])
    assert "Overview" in html and "Market" in html and "<p>Hello</p>" in html
    assert 'href="#s1"' in html
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/test_build_site.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tools'` (add an empty `tools/__init__.py` in the next step)

- [ ] **Step 4: Write tools/__init__.py and tools/build_site.py**

`tools/__init__.py`: empty file.

`tools/build_site.py`:
```python
"""Render status.yaml, crawl checkpoints, model metrics and docs/product/*.md into site/."""
from __future__ import annotations

import html
import json
from pathlib import Path

import markdown
import yaml

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"

CSS = """
:root{--ink:#161925;--ink2:#4b5268;--ink3:#7c849c;--rule:#dce0ec;--bg:#f1f3f8;--card:#fff;--brand:#2a3a93;--ok:#15755b;--warn:#a5620b}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 -apple-system,Segoe UI,Roboto,sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:32px 24px}header{display:flex;justify-content:space-between;align-items:baseline;gap:16px;flex-wrap:wrap;border-bottom:2px solid var(--ink);padding-bottom:12px;margin-bottom:28px}
h1{font-size:28px;margin:0;letter-spacing:-.02em}h2{font-size:20px;margin:32px 0 12px}h3{font-size:16px;margin:0 0 6px}
.nav a{color:var(--brand);margin-left:16px;text-decoration:none;font-weight:600}
.grid{display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(240px,1fr))}
.card{background:var(--card);border:1px solid var(--rule);border-radius:6px;padding:16px 18px;box-shadow:0 1px 2px rgba(0,0,0,.04)}
.big{font-size:44px;font-weight:700;line-height:1;margin:6px 0}.muted{color:var(--ink3);font-size:13px;text-transform:uppercase;letter-spacing:.08em}
.bar{height:10px;background:var(--rule);border-radius:5px;overflow:hidden;margin:10px 0}.bar i{display:block;height:100%;background:var(--brand)}
ul{padding-left:18px;margin:8px 0}li{margin:4px 0}.tag{font-size:11px;padding:2px 7px;border-radius:3px;background:#e5e9fa;color:var(--brand);margin-left:6px;text-transform:uppercase}
.tag.fahim{background:#fbefd8;color:var(--warn)}.tag.done{background:#ddf0e8;color:var(--ok)}
table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--rule)}th{color:var(--ink3);font-size:12px;text-transform:uppercase}
.toc{columns:2;gap:24px;font-size:14px}.toc a{display:block;color:var(--ink2);text-decoration:none;padding:2px 0}
article{background:var(--card);border:1px solid var(--rule);border-radius:6px;padding:28px 32px;margin-top:20px}article h2{margin-top:0}
footer{margin-top:40px;color:var(--ink3);font-size:12px}
"""


def compute_progress(status: dict) -> dict:
    tasks = [dict(t, phase=ph["name"]) for ph in status["phases"] for t in ph["tasks"]]
    total_w = sum(t["weight"] for t in tasks) or 1
    done_w = sum(t["weight"] for t in tasks if t["state"] == "done")
    phases = []
    for ph in status["phases"]:
        pw = sum(t["weight"] for t in ph["tasks"]) or 1
        pd = sum(t["weight"] for t in ph["tasks"] if t["state"] == "done")
        phases.append({"id": ph["id"], "name": ph["name"], "percent": round(100 * pd / pw), "tasks": ph["tasks"]})
    pending = [t for t in tasks if t["state"] != "done"]
    return {
        "percent": round(100 * done_w / total_w),
        "done_count": sum(1 for t in tasks if t["state"] == "done"),
        "total_count": len(tasks),
        "done": [t for t in tasks if t["state"] == "done"],
        "next_steps": pending[:3],
        "fahim_tasks": [t for t in pending if t["owner"] == "fahim"],
        "phases": phases,
    }


def _page(title: str, body: str, active: str) -> str:
    nav = "".join(
        f'<a href="{href}"{" style=text-decoration:underline" if key == active else ""}>{label}</a>'
        for key, href, label in (("dash", "index.html", "Dashboard"), ("doc", "doc.html", "Product document"), ("repo", "https://github.com/AhmedFahim13/bidefy", "Repo"))
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>{CSS}</style></head><body><div class="wrap">
<header><h1>{html.escape(title)}</h1><nav class="nav">{nav}</nav></header>{body}
<footer>Built from status.yaml by tools/build_site.py. Zero production cost.</footer></div></body></html>"""


def _task_li(t: dict) -> str:
    tag = f'<span class="tag {"fahim" if t["owner"] == "fahim" else ""}">{t["owner"]}</span>'
    note = f' <span style="color:var(--ink3)">{html.escape(t["note"])}</span>' if t.get("note") else ""
    return f"<li>{html.escape(t['title'])}{tag}{note}</li>"


def render_dashboard(status: dict, p: dict, crawl: dict, metrics: dict | None) -> str:
    crawl_rows = "".join(
        f"<tr><td>{html.escape(ep)}</td><td>{c.get('next_page', 1) - 1:,} / {c.get('total_pages', 0):,}</td>"
        f"<td>{html.escape(c.get('last_run_status', ''))}</td><td>{html.escape(c.get('updated_at', ''))}</td></tr>"
        for ep, c in crawl.items()
    ) or "<tr><td colspan=4>No crawl yet</td></tr>"
    metrics_html = (
        "<table><tr><th>Model</th><th>Metric</th><th>Value</th></tr>"
        + "".join(f"<tr><td>{html.escape(m)}</td><td>{html.escape(k)}</td><td>{v}</td></tr>" for m, d in metrics.items() for k, v in d.items())
        + "</table>"
        if metrics else "<p style='color:var(--ink3)'>No models trained yet. First model lands in week 4.</p>"
    )
    phases_html = "".join(
        f"<div class='card'><h3>{html.escape(ph['name'])}</h3><div class='bar'><i style='width:{ph['percent']}%'></i></div>"
        f"<div class='muted'>{ph['percent']}%</div><ul>{''.join(_task_li(t) for t in ph['tasks'])}</ul></div>"
        for ph in p["phases"]
    )
    body = f"""
<div class="grid">
  <div class="card"><div class="muted">Overall progress</div><div class="big">{p['percent']}%</div>
    <div class="bar"><i style="width:{p['percent']}%"></i></div><div class="muted">{p['done_count']} of {p['total_count']} tasks done. Launch target {html.escape(str(status.get('launch_target', '')))}</div></div>
  <div class="card"><div class="muted">Next three steps</div><ul>{''.join(_task_li(t) for t in p['next_steps'])}</ul></div>
  <div class="card"><div class="muted">Tasks only Fahim can do</div><ul>{''.join(_task_li(t) for t in p['fahim_tasks']) or '<li>None open</li>'}</ul></div>
</div>
<h2>Crawl</h2><div class="card"><table><tr><th>Endpoint</th><th>Pages</th><th>Last run</th><th>Updated</th></tr>{crawl_rows}</table></div>
<h2>Models</h2><div class="card">{metrics_html}</div>
<h2>Done</h2><div class="card"><ul>{''.join(_task_li(t) for t in p['done']) or '<li>Nothing yet</li>'}</ul></div>
<h2>Phases</h2><div class="grid">{phases_html}</div>"""
    return _page(f"{status['project']} command centre", body, "dash")


def render_doc(status: dict, sections: list[tuple[str, str]]) -> str:
    toc = "".join(f'<a href="#s{i}">{i}. {html.escape(t)}</a>' for i, (t, _) in enumerate(sections, 1))
    body = f'<div class="card"><div class="muted">Contents</div><div class="toc">{toc}</div></div>' + "".join(
        f'<article id="s{i}"><h2>{i}. {html.escape(t)}</h2>{b}</article>' for i, (t, b) in enumerate(sections, 1)
    )
    return _page(f"{status['project']} product document", body, "doc")


def load_sections(doc_dir: Path) -> list[tuple[str, str]]:
    out = []
    for path in sorted(doc_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        first, _, rest = text.partition("\n")
        title = first.lstrip("# ").strip() if first.startswith("#") else path.stem
        out.append((title, markdown.markdown(rest if first.startswith("#") else text, extensions=["tables"])))
    return out


def main() -> None:
    status = yaml.safe_load((ROOT / "status.yaml").read_text(encoding="utf-8"))
    crawl = {}
    for path in sorted((ROOT / "checkpoints").glob("*.json")) if (ROOT / "checkpoints").exists() else []:
        crawl[path.stem] = json.loads(path.read_text(encoding="utf-8"))
    metrics_path = ROOT / "models" / "metrics.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.exists() else None
    p = compute_progress(status)
    SITE.mkdir(exist_ok=True)
    (SITE / "index.html").write_text(render_dashboard(status, p, crawl, metrics), encoding="utf-8")
    (SITE / "doc.html").write_text(render_doc(status, load_sections(ROOT / "docs" / "product")), encoding="utf-8")
    print(f"site built: {p['percent']}% complete, {len(crawl)} checkpoints, {len(list((ROOT / 'docs' / 'product').glob('*.md')))} doc sections")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_build_site.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add status.yaml tools/__init__.py tools/build_site.py tests/test_build_site.py
git commit -m "Add command centre source of truth and site builder"
```

---

### Task 12: First product document section and a local build

**Files:**
- Create: `docs/product/00-overview.md`

- [ ] **Step 1: Write the overview section**

```markdown
# Overview

Bidefy is tender intelligence for Bangladesh's public procurement portal, e-GP. It indexes every public tender notice and contract award, resolves the messy names of bidders and procuring entities into stable identities, predicts the likely award value of a live tender, flags unusual award patterns with the numbers behind them, and sends web push alerts when a tender matching a subscriber's filters appears.

## The gap it fills

Existing services sell daily notice alerts filtered by category, district and organisation, at roughly 1,050 taka a month. None of them use the 877,000 public contract awards on the same portal. So none can answer the questions a bidder actually has: who wins this kind of tender at this entity, at what value, and how often. Bidefy is that layer. It does not compete on alerts.

## What is deliberately not built

- No WhatsApp or Telegram in version one. Web push only, because it costs nothing and needs no Meta account.
- No payments. The Pro tier shows a request-access form until there is a merchant account.
- No claim of fraud. Flags describe patterns with counts and intervals, never a verdict.
- No mirroring of raw notices. The product publishes derived intelligence.

## Cost

Production cost is zero. GitHub Actions crawls and trains, Cloudflare Workers and D1 serve the site and send push, GitHub Pages hosts this document and the command centre.

## Source facts

| Fact | Value |
|---|---|
| Tender notices indexed | about 625,800 |
| Contract awards indexed | about 877,200 |
| Request rate | one per second, one session, checkpointed |
| Data not published by the portal | losing bids, bidder counts, official cost estimates |

The tender security amount, which each procuring entity sets as a share of its estimate, is the cost proxy for prediction.
```

- [ ] **Step 2: Build the site locally and open it**

Run: `uv run python tools/build_site.py && ls site`
Expected: `site built: N% complete, 1 checkpoints, 1 doc sections` and `doc.html index.html`. Open `site/index.html` in the browser pane and confirm the three cards, the crawl table with the tenders row, and the phases grid render; open `site/doc.html` and confirm the contents list links to section 1.

- [ ] **Step 3: Commit**

```bash
git add docs/product/00-overview.md
git commit -m "Add product overview section"
```

---

### Task 13: Pages workflow and deployment

**Files:**
- Create: `.github/workflows/pages.yml`
- Modify: `README.md`

- [ ] **Step 1: Write the workflow**

`.github/workflows/pages.yml`:
```yaml
name: Command centre

on:
  push:
    branches: [main]
    paths:
      - status.yaml
      - checkpoints/**
      - models/metrics.json
      - docs/product/**
      - tools/build_site.py
      - .github/workflows/pages.yml
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: true

jobs:
  build:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync
      - run: uv run python tools/build_site.py
      - uses: actions/upload-pages-artifact@v3
        with:
          path: site
  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - id: deployment
        uses: actions/deploy-pages@v4
```

- [ ] **Step 2: Enable Pages for Actions deployment**

Run: `gh api -X POST repos/AhmedFahim13/bidefy/pages -f build_type=workflow 2>&1 | head -c 300; true`
Expected: JSON with `"build_type":"workflow"`, or a 409 saying Pages already exists. Both are fine.

- [ ] **Step 3: Commit, push, watch the deploy**

```bash
git add .github/workflows/pages.yml
git commit -m "Deploy command centre to GitHub Pages"
git pull --rebase
git push
```
Then: `sleep 60 && gh run list --workflow "Command centre" --limit 1` and once it completes: `gh api repos/AhmedFahim13/bidefy/pages --jq .html_url`
Expected: `https://ahmedfahim13.github.io/bidefy/`. Open it in the browser pane and confirm the dashboard renders.

- [ ] **Step 4: Put the link in the README and mark the centre done in status.yaml**

In `README.md` replace `Command centre: published by the Pages workflow (link added once live)` with `Command centre: https://ahmedfahim13.github.io/bidefy/ (dashboard) and https://ahmedfahim13.github.io/bidefy/doc.html (product document)`.

In `status.yaml` change task `w1-centre` from `state: doing` to `state: done`.

- [ ] **Step 5: Commit and push**

```bash
git add README.md status.yaml
git commit -m "Link command centre; mark it done"
git pull --rebase
git push
```

---

## Self-review against the spec

- Spec 5.1 crawler: Tasks 8, 9, 10. Rate limit, checkpoint per page, three-failure abort, delta stop rule, multi-night backfill: covered. Detail-page queue for live tenders is not in this plan; it lands with the modelling sample in the week 4 plan, and `parse_detail` (Task 5) plus `EgpSession.detail` (Task 8) are ready for it.
- Spec 5.2 to 5.5: week 2 onward, separate plans.
- Spec 6 command centre: Tasks 11, 12, 13. Percent by weight, done, next three, Fahim's tasks, crawl time, metrics, doc page with the Auto structure started by section 1.
- Spec 7 testing: parsers on fixtures (Tasks 3 to 5), CI (Task 1). Entity resolution and Worker tests belong to later plans.
- Spec 10 Fahim's tasks: all nine appear in `status.yaml` with `owner: fahim`.
- Names used consistently: `parse_tender_rows`, `parse_contract_rows`, `parse_detail`, `Checkpoint`, `append_rows`, `known_ids`, `load_all`, `EgpSession.list_page`, `EgpSession.detail`, `run.crawl`, `Summary`, `compute_progress`, `render_dashboard`, `render_doc`.
