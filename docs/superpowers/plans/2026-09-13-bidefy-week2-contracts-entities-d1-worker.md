# Bidefy Week 2: Contracts, Entity Resolution, D1 and Worker API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task inline. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Contract awards crawling, stable identities for bidders and procuring entities with a human review queue, a nightly loader into Cloudflare D1 that respects the free tier's daily write cap, and a deployed Worker API on workers.dev serving tenders, contracts, bidders and procuring entities from D1.

**Architecture:** Two new Python subpackages: `bidefy.normalize` (name normalisation, blocked TF-IDF resolution, clean tables) and `bidefy.export` (D1 batch SQL with a watermark and row cap, executed through wrangler). A `worker/` directory holds a Hono TypeScript Worker bound to the `bidefy` D1 database, with pure query builders unit-tested by vitest. The frontend is out of scope this week; it goes on Vercel in week 3 and calls this API.

**Tech Stack:** Python 3.12, polars, scikit-learn, pytest; Node 25, wrangler 4, Hono, vitest, TypeScript. D1 database `bidefy` id `9a19c0e9-6e01-4066-8615-8eee5267ce2c`, account `7d11f8ace9e7f5b9061cbc8decf97bc8`.

Spec: `docs/superpowers/specs/2026-09-13-bidefy-design.md`, sections 5.2, 5.4, 5.5.

---

## File structure

```
bidefy/normalize/__init__.py
bidefy/normalize/names.py        normalize_name, block_key
bidefy/normalize/resolve.py      resolve(), Resolution, review CSV read and write
bidefy/normalize/build.py        CLI: raw parquet -> data/clean/*.parquet + review/pairs.csv
bidefy/export/__init__.py
bidefy/export/d1.py              CLI: clean parquet -> batched SQL -> wrangler d1 execute, watermark
worker/package.json
worker/tsconfig.json
worker/wrangler.jsonc
worker/schema.sql
worker/src/index.ts              Hono app, routes, scheduled stub
worker/src/query.ts              pure SQL builders
worker/test/query.test.ts
tests/test_names.py
tests/test_resolve.py
tests/test_build_clean.py
tests/test_d1_export.py
review/pairs.csv                 created by build, committed
checkpoints/d1_load.json         loader watermark, committed
docs/product/01-market.md
```

Conventions unchanged from week 1: LF endings, no em dashes, commit after every task with the trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`, `git pull --rebase` before every push. No requests to eprocure.gov.bd from tests. The crawl concurrency group serialises Actions runs, so a dispatched contracts run queues behind the tender backfill.

---

### Task 1: Queue the contracts backfill and record the loader constraint

**Files:**
- Modify: `status.yaml`

- [ ] **Step 1: Dispatch the contracts backfill on Actions**

Run: `cd C:/Users/hp/Auto/egp-intel && gh workflow run "Crawl e-GP" -f endpoint=contracts -f mode=backfill -f budget_min=300 && sleep 20 && gh run list --workflow "Crawl e-GP" --limit 2`
Expected: two rows, the tender run `in_progress` and the contracts run `queued` (the concurrency group holds it until the tender run ends).

- [ ] **Step 2: Add the week 2 tasks that need Fahim**

In `status.yaml` under phase `w2`, replace the `w2-domain` task with:
```yaml
      - {id: w2-domain, title: "Stay on workers.dev", owner: fahim, state: done, weight: 1}
      - {id: w2-token, title: "Create a Cloudflare API token with D1 edit rights and add it as the CLOUDFLARE_API_TOKEN repo secret", owner: fahim, state: todo, weight: 2, note: "Needed for the nightly Actions loader; local loads work with your wrangler login"}
```
and mark `w1-cloudflare` and `w1-terms` as `state: done`. Under phase `w5`, replace the `w5-price` task with:
```yaml
      - {id: w5-personas, title: "Five data-derived buyer profiles from the awards table, labelled as such", owner: claude, state: todo, weight: 2}
      - {id: w5-signals, title: "Request-access form live and collecting real pricing signals", owner: claude, state: todo, weight: 2}
```

- [ ] **Step 3: Commit and push**

```bash
git add status.yaml
git commit -m "Queue contracts backfill; update week 2 and 5 tasks"
git pull --rebase
git push
```

---

### Task 2: Name normalisation and blocking

**Files:**
- Create: `bidefy/normalize/__init__.py`
- Create: `bidefy/normalize/names.py`
- Create: `tests/test_names.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_names.py`:
```python
from bidefy.normalize.names import block_key, normalize_name


def test_strips_ms_prefix_and_punctuation():
    assert normalize_name("M/S. Sawda Traders") == "sawda traders"
    assert normalize_name("M/S Sawda Traders.") == "sawda traders"
    assert normalize_name("Messrs. SAWDA   TRADERS") == "sawda traders"
    assert normalize_name("MS Sawda Traders") == "sawda traders"


def test_keeps_type_words_and_maps_ampersand():
    assert normalize_name("Z S Technologies Ltd.") == "z s technologies ltd"
    assert normalize_name("Rahim & Sons Enterprise") == "rahim and sons enterprise"
    assert normalize_name("PTA Infrastructure (Pvt.) Limited") == "pta infrastructure pvt limited"


def test_unicode_and_empty():
    assert normalize_name("  ") == ""
    assert normalize_name("\u09b8\u09be\u0993\u09a6\u09be \u099f\u09cd\u09b0\u09c7\u09a1\u09be\u09b0\u09cd\u09b8") == "\u09b8\u09be\u0993\u09a6\u09be \u099f\u09cd\u09b0\u09c7\u09a1\u09be\u09b0\u09cd\u09b8"


def test_block_key_is_first_token_of_three_or_more_letters():
    assert block_key("sawda traders") == "sawda"
    assert block_key("z s technologies ltd") == "technologies"
    assert block_key("ab") == "ab"
    assert block_key("") == ""
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_names.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bidefy.normalize'`

- [ ] **Step 3: Write the module**

`bidefy/normalize/__init__.py`:
```python
"""Turn raw e-GP rows into clean tables with stable bidder and procuring entity ids."""
```

`bidefy/normalize/names.py`:
```python
"""Normalise firm names so spelling variants compare equal, and pick a blocking key."""
from __future__ import annotations

import re
import unicodedata

_PREFIX_RE = re.compile(r"^(?:m\s*/\s*s\.?|messrs\.?|ms\.?)\s+", re.I)
_PUNCT_RE = re.compile(r"[^\w\s]", re.U)
_SPACE_RE = re.compile(r"\s+")


def normalize_name(raw: str) -> str:
    """Lowercase, NFKC, drop M/S style prefixes, map & to and, strip punctuation, collapse spaces."""
    text = unicodedata.normalize("NFKC", raw or "").strip().lower()
    text = _PREFIX_RE.sub("", text)
    text = text.replace("&", " and ")
    text = _PUNCT_RE.sub(" ", text)
    text = _SPACE_RE.sub(" ", text).strip()
    return text


def block_key(normalized: str) -> str:
    """First token with three or more characters; falls back to the first token or ''."""
    tokens = normalized.split()
    for tok in tokens:
        if len(tok) >= 3:
            return tok
    return tokens[0] if tokens else ""
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_names.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add bidefy/normalize tests/test_names.py
git commit -m "Add firm name normalisation and blocking key"
```

---

### Task 3: Entity resolution with a review queue

Within each block, char n-gram TF-IDF cosine similarity. Pairs at or above 0.92 merge automatically, pairs from 0.80 to 0.92 go to a review CSV, decisions in that CSV override the thresholds. Entity ids are stable hashes of the canonical normalised name.

**Files:**
- Create: `bidefy/normalize/resolve.py`
- Create: `tests/test_resolve.py`
- Modify: `pyproject.toml` (add scikit-learn)

- [ ] **Step 1: Add the dependency**

Run: `uv add "scikit-learn>=1.4"`
Expected: pyproject.toml gains the dependency and uv.lock updates.

- [ ] **Step 2: Write the failing tests**

`tests/test_resolve.py`:
```python
from pathlib import Path

from bidefy.normalize import resolve as r


def test_merges_close_variants_and_keeps_distinct_firms():
    counts = {
        "M/S Sawda Traders": 5, "M/S. SAWDA TRADERS": 3, "Sawda Traders": 1,
        "Sawda Trading Corporation": 2, "Hamida Traders": 4,
    }
    res = r.resolve(counts)
    ids = res.entity_of
    assert ids["M/S Sawda Traders"] == ids["M/S. SAWDA TRADERS"] == ids["Sawda Traders"]
    assert ids["Hamida Traders"] != ids["M/S Sawda Traders"]
    sawda = next(e for e in res.entities if e["entity_id"] == ids["M/S Sawda Traders"])
    assert sawda["canonical_name"] == "M/S Sawda Traders"          # most frequent raw spelling
    assert sawda["n_rows"] == 9
    assert sorted(sawda["variants"]) == ["M/S Sawda Traders", "M/S. SAWDA TRADERS", "Sawda Traders"]


def test_borderline_pairs_go_to_review_not_merge():
    counts = {"Rahim Construction": 3, "Rahim Constructions Ltd": 2}
    res = r.resolve(counts, merge_threshold=0.99, review_threshold=0.50)
    assert res.entity_of["Rahim Construction"] != res.entity_of["Rahim Constructions Ltd"]
    assert len(res.review_pairs) == 1
    a, b, score = res.review_pairs[0]
    assert {a, b} == {"Rahim Construction", "Rahim Constructions Ltd"} and 0.5 <= score < 0.99


def test_review_decisions_override(tmp_path: Path):
    csv = tmp_path / "pairs.csv"
    counts = {"Rahim Construction": 3, "Rahim Constructions Ltd": 2, "Karim Traders": 1, "Karim Trader": 1}
    first = r.resolve(counts, merge_threshold=0.99, review_threshold=0.50)
    r.write_review(csv, first.review_pairs, existing=r.read_review(csv))
    text = csv.read_text(encoding="utf-8")
    assert text.startswith("a,b,score,decision")
    decided = text.replace("Rahim Construction,Rahim Constructions Ltd,", "Rahim Construction,Rahim Constructions Ltd,", 1)
    lines = decided.splitlines()
    lines = [l + "merge" if l.startswith("Rahim Construction,") else (l + "keep" if l.startswith("Karim") else l) for l in lines]
    csv.write_text("\n".join(lines) + "\n", encoding="utf-8")
    decisions = r.read_review(csv)
    second = r.resolve(counts, merge_threshold=0.99, review_threshold=0.50, decisions=decisions)
    assert second.entity_of["Rahim Construction"] == second.entity_of["Rahim Constructions Ltd"]
    assert second.entity_of["Karim Traders"] != second.entity_of["Karim Trader"]
    assert second.review_pairs == []                       # decided pairs are not re-queued


def test_entity_ids_are_stable_across_runs():
    a = r.resolve({"Hamida Traders": 1, "Other Firm": 1})
    b = r.resolve({"Other Firm": 9, "Hamida Traders": 2, "New Firm": 1})
    assert a.entity_of["Hamida Traders"] == b.entity_of["Hamida Traders"]
    assert len(a.entity_of["Hamida Traders"]) == 12


def test_empty_and_blank_names():
    res = r.resolve({"": 3, "   ": 1, "Real Firm": 1})
    assert res.entity_of[""] == "" and res.entity_of["   "] == ""
    assert len(res.entities) == 1
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/test_resolve.py -v`
Expected: FAIL with `ImportError: cannot import name 'resolve'`

- [ ] **Step 4: Write resolve.py**

```python
"""Group raw firm names into entities: blocked char n-gram TF-IDF, thresholds, and a review CSV."""
from __future__ import annotations

import csv
import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer

from .names import block_key, normalize_name

MERGE_THRESHOLD = 0.92
REVIEW_THRESHOLD = 0.80
MAX_BLOCK = 4000          # blocks above this size are split by the second token
Decision = dict[tuple[str, str], str]   # (raw_a, raw_b) sorted -> "merge" | "keep"


@dataclass
class Resolution:
    entity_of: dict[str, str] = field(default_factory=dict)       # raw name -> entity_id ('' for blank)
    entities: list[dict] = field(default_factory=list)             # entity_id, canonical_name, variants, n_rows
    review_pairs: list[tuple[str, str, float]] = field(default_factory=list)


class _UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def entity_id(canonical_normalized: str) -> str:
    return hashlib.sha1(canonical_normalized.encode("utf-8")).hexdigest()[:12]


def _pair_key(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a <= b else (b, a)


def _blocks(norms: list[str]) -> dict[str, list[int]]:
    blocks: dict[str, list[int]] = defaultdict(list)
    for i, n in enumerate(norms):
        blocks[block_key(n)].append(i)
    out: dict[str, list[int]] = {}
    for key, idx in blocks.items():
        if len(idx) <= MAX_BLOCK:
            out[key] = idx
            continue
        sub: dict[str, list[int]] = defaultdict(list)
        for i in idx:
            toks = norms[i].split()
            sub[key + "|" + (toks[1] if len(toks) > 1 else "")].append(i)
        out.update(sub)
    return out


def _similar_pairs(norms: list[str], idx: list[int], floor: float) -> list[tuple[int, int, float]]:
    if len(idx) < 2:
        return []
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
    m = vec.fit_transform([norms[i] for i in idx])
    sims = (m @ m.T).tocoo()
    pairs = []
    for r_, c_, v in zip(sims.row, sims.col, sims.data):
        if r_ < c_ and v >= floor:
            pairs.append((idx[r_], idx[c_], float(v)))
    return pairs


def resolve(
    counts: dict[str, int],
    merge_threshold: float = MERGE_THRESHOLD,
    review_threshold: float = REVIEW_THRESHOLD,
    decisions: Decision | None = None,
) -> Resolution:
    """counts maps each raw name to how many rows carry it. Blank names resolve to ''."""
    decisions = decisions or {}
    raws = [r for r in counts if normalize_name(r)]
    norms = [normalize_name(r) for r in raws]
    # identical normalised strings merge before any similarity work
    first_of: dict[str, int] = {}
    uf = _UnionFind(len(raws))
    for i, n in enumerate(norms):
        if n in first_of:
            uf.union(first_of[n], i)
        else:
            first_of[n] = i
    review: list[tuple[str, str, float]] = []
    for idx in _blocks(norms).values():
        for i, j, score in _similar_pairs(norms, idx, review_threshold):
            key = _pair_key(raws[i], raws[j])
            decided = decisions.get(key)
            if decided == "merge" or (decided is None and score >= merge_threshold):
                uf.union(i, j)
            elif decided is None:
                review.append((key[0], key[1], round(score, 4)))
    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(len(raws)):
        groups[uf.find(i)].append(i)
    res = Resolution()
    for members in groups.values():
        members.sort(key=lambda i: (-counts[raws[i]], raws[i]))
        canonical_raw = raws[members[0]]
        eid = entity_id(normalize_name(canonical_raw))
        for i in members:
            res.entity_of[raws[i]] = eid
        res.entities.append({
            "entity_id": eid,
            "canonical_name": canonical_raw,
            "variants": [raws[i] for i in members],
            "n_rows": sum(counts[raws[i]] for i in members),
        })
    for r in counts:
        if r not in res.entity_of:
            res.entity_of[r] = ""
    res.entities.sort(key=lambda e: (-e["n_rows"], e["canonical_name"]))
    res.review_pairs = sorted(set(review), key=lambda p: (-p[2], p[0], p[1]))
    return res


def read_review(path: Path) -> Decision:
    """Decided rows only. Undecided rows are ignored so they can be re-queued."""
    out: Decision = {}
    if not Path(path).exists():
        return out
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            d = (row.get("decision") or "").strip().lower()
            if d in ("merge", "keep"):
                out[_pair_key(row["a"], row["b"])] = d
    return out


def write_review(path: Path, pairs: list[tuple[str, str, float]], existing: Decision) -> int:
    """Rewrite the CSV: decided rows first (kept verbatim), then the current undecided pairs."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [(a, b, "", d) for (a, b), d in sorted(existing.items())]
    rows += [(a, b, f"{s:.4f}", "") for a, b, s in pairs if _pair_key(a, b) not in existing]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["a", "b", "score", "decision"])
        w.writerows(rows)
    return len(rows)
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_resolve.py -v`
Expected: 5 passed. If `test_merges_close_variants_and_keeps_distinct_firms` fails because "Sawda Trading Corporation" merged with "Sawda Traders", print the score and raise nothing else: the fix is the default merge threshold, which must stay at 0.92; adjust the test names only if the score is genuinely above 0.92 (it should be near 0.6).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock bidefy/normalize/resolve.py tests/test_resolve.py
git commit -m "Add blocked TF-IDF entity resolution with a review queue"
```

---

### Task 4: Clean tables builder

Reads raw Parquet through `store.load_all`, resolves bidders and procuring entities, writes `data/clean/*.parquet`, and maintains `review/pairs.csv`. Runs nightly after compaction.

**Files:**
- Create: `bidefy/normalize/build.py`
- Create: `tests/test_build_clean.py`
- Modify: `.github/workflows/crawl.yml`

- [ ] **Step 1: Write the failing tests**

`tests/test_build_clean.py`:
```python
from pathlib import Path

import polars as pl

from bidefy.crawler import store
from bidefy.normalize import build


def _tender(i, pe="Taxes Zone-Faridpur", status="Live"):
    return {"tender_id": str(i), "reference": f"R{i}", "status": status, "note": "", "nature": "Goods",
            "title": f"Tender {i}", "ministry": "Ministry of Finance", "organization": "NBR",
            "procuring_entity": pe, "procurement_type": "NCT", "method": "OTM",
            "published_at": "2026-09-01T10:00", "closing_at": "2026-09-20T10:00"}


def _contract(i, awardee, pe="Taxes Zone-Faridpur", value=0.5):
    return {"tender_id": str(i), "reference": f"R{i}", "title": f"Contract {i}", "advertised_at": "2026-08-01T10:00",
            "ministry": "Ministry of Finance", "procuring_entity": pe, "method": "OTM", "district": "Faridpur",
            "signed_on": "2026-09-0%d" % (1 + i % 8), "awardee": awardee, "value_crore": value}


def _seed(root: Path):
    store.append_rows([_tender(1), _tender(2, status="Cancelled"), _tender(3, pe="Kushtia PBS")], root, "tenders")
    store.append_rows([_contract(1, "M/S Sawda Traders", value=1.0), _contract(2, "M/S. SAWDA TRADERS"),
                       _contract(3, "Hamida Traders", pe="Kushtia PBS"), _contract(4, "")], root, "contracts")


def test_build_writes_clean_tables_with_stable_ids(tmp_path: Path):
    _seed(tmp_path)
    out = build.build(tmp_path, tmp_path / "review" / "pairs.csv")
    bidders = pl.read_parquet(tmp_path / "clean" / "bidders.parquet")
    contracts = pl.read_parquet(tmp_path / "clean" / "contracts.parquet")
    pes = pl.read_parquet(tmp_path / "clean" / "procuring_entities.parquet")
    tenders = pl.read_parquet(tmp_path / "clean" / "tenders.parquet")
    assert out["bidders"] == 2 and bidders.height == 2
    sawda = bidders.filter(pl.col("canonical_name") == "M/S Sawda Traders").row(0, named=True)
    assert sawda["n_awards"] == 2 and abs(sawda["total_value_crore"] - 1.5) < 1e-9
    assert sawda["first_award"] == "2026-09-02" and sawda["last_award"] == "2026-09-03"
    assert contracts.filter(pl.col("tender_id") == "4")["bidder_id"][0] == ""      # blank awardee
    assert set(contracts["bidder_id"].unique().to_list()) >= {sawda["bidder_id"]}
    assert pes.height == 2 and set(pes.columns) >= {"pe_id", "name", "ministry", "n_contracts", "n_tenders"}
    faridpur = pes.filter(pl.col("name") == "Taxes Zone-Faridpur").row(0, named=True)
    assert faridpur["n_contracts"] == 3 and faridpur["n_tenders"] == 2
    assert tenders.height == 3 and "pe_id" in tenders.columns
    assert tenders.filter(pl.col("tender_id") == "1")["pe_id"][0] == faridpur["pe_id"]
    assert (tmp_path / "review" / "pairs.csv").exists()


def test_build_is_idempotent_and_keeps_ids(tmp_path: Path):
    _seed(tmp_path)
    build.build(tmp_path, tmp_path / "review" / "pairs.csv")
    first = pl.read_parquet(tmp_path / "clean" / "bidders.parquet").sort("bidder_id")
    build.build(tmp_path, tmp_path / "review" / "pairs.csv")
    second = pl.read_parquet(tmp_path / "clean" / "bidders.parquet").sort("bidder_id")
    assert first["bidder_id"].to_list() == second["bidder_id"].to_list()


def test_build_with_no_raw_data(tmp_path: Path):
    out = build.build(tmp_path, tmp_path / "review" / "pairs.csv")
    assert out == {"tenders": 0, "contracts": 0, "bidders": 0, "procuring_entities": 0, "review_pairs": 0}
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_build_clean.py -v`
Expected: FAIL with `ImportError: cannot import name 'build'`

- [ ] **Step 3: Write build.py**

```python
"""Build data/clean/*.parquet from the raw store and maintain the review CSV."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import polars as pl

from ..crawler import store
from . import resolve as r
from .names import normalize_name

EMPTY = {"tenders": 0, "contracts": 0, "bidders": 0, "procuring_entities": 0, "review_pairs": 0}


def _pe_id(name: str) -> str:
    n = normalize_name(name)
    return r.entity_id("pe:" + n) if n else ""


def _write(df: pl.DataFrame, root: Path, name: str) -> None:
    out = root / "clean"
    out.mkdir(parents=True, exist_ok=True)
    tmp = out / f"{name}.parquet.tmp"
    df.write_parquet(tmp, compression="zstd")
    tmp.replace(out / f"{name}.parquet")


def build(data_root: Path, review_path: Path) -> dict:
    data_root = Path(data_root)
    tenders = store.load_all(data_root, "tenders")
    contracts = store.load_all(data_root, "contracts")
    if tenders.is_empty() and contracts.is_empty():
        return dict(EMPTY)

    # bidders
    counts: dict[str, int] = {}
    if not contracts.is_empty():
        for name, n in contracts.group_by("awardee").len().iter_rows():
            counts[name or ""] = int(n)
    decisions = r.read_review(review_path)
    res = r.resolve(counts, decisions=decisions)
    n_pairs = r.write_review(review_path, res.review_pairs, decisions)

    if not contracts.is_empty():
        contracts = contracts.with_columns(
            pl.col("awardee").fill_null("").map_elements(lambda a: res.entity_of.get(a, ""), return_dtype=pl.Utf8).alias("bidder_id"),
            pl.col("procuring_entity").fill_null("").map_elements(_pe_id, return_dtype=pl.Utf8).alias("pe_id"),
        )
        _write(contracts, data_root, "contracts")
        awarded = contracts.filter(pl.col("bidder_id") != "")
        stats = awarded.group_by("bidder_id").agg(
            pl.len().alias("n_awards"),
            pl.col("value_crore").fill_null(0.0).sum().alias("total_value_crore"),
            pl.col("signed_on").min().alias("first_award"),
            pl.col("signed_on").max().alias("last_award"),
        )
        meta = pl.DataFrame([
            {"bidder_id": e["entity_id"], "canonical_name": e["canonical_name"], "variants": json.dumps(e["variants"], ensure_ascii=False)}
            for e in res.entities
        ])
        bidders = meta.join(stats, on="bidder_id", how="left").fill_null(0).sort("n_awards", descending=True)
        _write(bidders, data_root, "bidders")
    else:
        bidders = pl.DataFrame({"bidder_id": [], "canonical_name": [], "variants": []})

    # tenders and procuring entities
    if not tenders.is_empty():
        tenders = tenders.with_columns(pl.col("procuring_entity").fill_null("").map_elements(_pe_id, return_dtype=pl.Utf8).alias("pe_id"))
        _write(tenders, data_root, "tenders")
    frames = []
    if not tenders.is_empty():
        frames.append(tenders.group_by("pe_id", "procuring_entity", "ministry").agg(pl.len().alias("n_tenders")).with_columns(pl.lit(0).alias("n_contracts")))
    if not contracts.is_empty():
        frames.append(contracts.group_by("pe_id", "procuring_entity", "ministry").agg(pl.len().alias("n_contracts")).with_columns(pl.lit(0).alias("n_tenders")))
    pes = (
        pl.concat(frames, how="diagonal_relaxed")
        .filter(pl.col("pe_id") != "")
        .group_by("pe_id").agg(
            pl.col("procuring_entity").first().alias("name"),
            pl.col("ministry").first().alias("ministry"),
            pl.col("n_contracts").sum(), pl.col("n_tenders").sum(),
        )
        .sort("n_contracts", descending=True)
    )
    _write(pes, data_root, "procuring_entities")
    return {
        "tenders": tenders.height, "contracts": contracts.height, "bidders": bidders.height,
        "procuring_entities": pes.height, "review_pairs": n_pairs,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build clean tables and the review queue")
    ap.add_argument("--data-root", default="data")
    ap.add_argument("--review", default="review/pairs.csv")
    a = ap.parse_args(argv)
    out = build(Path(a.data_root), Path(a.review))
    print("clean build: " + ", ".join(f"{k}={v}" for k, v in out.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_build_clean.py -v`
Expected: 3 passed. `n_contracts` for Faridpur is 3 because the blank-awardee contract still belongs to that entity.

- [ ] **Step 5: Run it on the real data and commit the outputs**

Run: `uv run python -m bidefy.normalize.build && ls data/clean && head -5 review/pairs.csv`
Expected: a line like `clean build: tenders=N, contracts=0, bidders=0, procuring_entities=M, review_pairs=0` (contracts are still crawling) and `tenders.parquet procuring_entities.parquet` present.

- [ ] **Step 6: Add the nightly step to the workflow**

In `.github/workflows/crawl.yml`, after the `Compact` step and before `Commit data`, insert:
```yaml
      - name: Build clean tables
        run: uv run python -m bidefy.normalize.build
```
and change `git add data checkpoints` to `git add data checkpoints review`.

- [ ] **Step 7: Commit and push**

```bash
git add bidefy/normalize/build.py tests/test_build_clean.py .github/workflows/crawl.yml data/clean review
git commit -m "Build clean tables with resolved bidders and procuring entities"
git pull --rebase
git push
```

---

### Task 5: D1 schema and the capped nightly loader

D1's free tier allows 100,000 row writes a day. The loader selects the recent window, orders by `fetched_at`, stops at a row cap, records a watermark, and continues the next night. It writes multi-row `INSERT OR REPLACE` statements to `.sql` files and executes them with wrangler.

**Files:**
- Create: `worker/schema.sql`
- Create: `bidefy/export/__init__.py`
- Create: `bidefy/export/d1.py`
- Create: `tests/test_d1_export.py`

- [ ] **Step 1: Write the schema**

`worker/schema.sql`:
```sql
CREATE TABLE IF NOT EXISTS tenders (
  tender_id TEXT PRIMARY KEY, reference TEXT, status TEXT, note TEXT, nature TEXT, title TEXT,
  ministry TEXT, organization TEXT, procuring_entity TEXT, pe_id TEXT, procurement_type TEXT,
  method TEXT, published_at TEXT, closing_at TEXT, fetched_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_tenders_published ON tenders(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_tenders_closing ON tenders(closing_at);
CREATE INDEX IF NOT EXISTS idx_tenders_status ON tenders(status);
CREATE INDEX IF NOT EXISTS idx_tenders_pe ON tenders(pe_id);

CREATE TABLE IF NOT EXISTS contracts (
  tender_id TEXT PRIMARY KEY, reference TEXT, title TEXT, advertised_at TEXT, ministry TEXT,
  procuring_entity TEXT, pe_id TEXT, method TEXT, district TEXT, signed_on TEXT, awardee TEXT,
  bidder_id TEXT, value_crore REAL, fetched_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_contracts_signed ON contracts(signed_on DESC);
CREATE INDEX IF NOT EXISTS idx_contracts_bidder ON contracts(bidder_id);
CREATE INDEX IF NOT EXISTS idx_contracts_pe ON contracts(pe_id);
CREATE INDEX IF NOT EXISTS idx_contracts_district ON contracts(district);

CREATE TABLE IF NOT EXISTS bidders (
  bidder_id TEXT PRIMARY KEY, canonical_name TEXT, variants TEXT, n_awards INTEGER,
  total_value_crore REAL, first_award TEXT, last_award TEXT
);
CREATE TABLE IF NOT EXISTS procuring_entities (
  pe_id TEXT PRIMARY KEY, name TEXT, ministry TEXT, n_contracts INTEGER, n_tenders INTEGER
);
CREATE TABLE IF NOT EXISTS subscriptions (
  id TEXT PRIMARY KEY, endpoint TEXT NOT NULL, keys_json TEXT NOT NULL, filters_json TEXT NOT NULL,
  created_at TEXT NOT NULL, last_sent_at TEXT
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
```

- [ ] **Step 2: Write the failing tests**

`tests/test_d1_export.py`:
```python
import json
from pathlib import Path

import polars as pl

from bidefy.export import d1


def _clean(root: Path):
    (root / "clean").mkdir(parents=True)
    pl.DataFrame([
        {"tender_id": "1", "reference": "r", "status": "Live", "note": "", "nature": "Goods", "title": "O'Brien supply",
         "ministry": "M", "organization": "", "procuring_entity": "PE", "pe_id": "p1", "procurement_type": "NCT",
         "method": "OTM", "published_at": "2026-09-01T10:00", "closing_at": "2026-09-20T10:00", "fetched_at": "20260913T070000000000Z"},
        {"tender_id": "2", "reference": "r", "status": "Cancelled", "note": "", "nature": "Goods", "title": "Old one",
         "ministry": "M", "organization": "", "procuring_entity": "PE", "pe_id": "p1", "procurement_type": "NCT",
         "method": "OTM", "published_at": "2024-01-01T10:00", "closing_at": "2024-01-20T10:00", "fetched_at": "20260913T070000000001Z"},
        {"tender_id": "3", "reference": "r", "status": "Live", "note": "", "nature": "Goods", "title": "Newer",
         "ministry": "M", "organization": "", "procuring_entity": "PE", "pe_id": "p1", "procurement_type": "NCT",
         "method": "OTM", "published_at": "2026-09-02T10:00", "closing_at": "2026-09-21T10:00", "fetched_at": "20260913T070000000002Z"},
    ]).write_parquet(root / "clean" / "tenders.parquet")
    pl.DataFrame([
        {"tender_id": "9", "reference": "r", "title": "C", "advertised_at": "2026-08-01T10:00", "ministry": "M",
         "procuring_entity": "PE", "pe_id": "p1", "method": "OTM", "district": "Dhaka", "signed_on": "2026-09-01",
         "awardee": "A", "bidder_id": "b1", "value_crore": 0.5, "fetched_at": "20260913T070000000003Z"},
    ]).write_parquet(root / "clean" / "contracts.parquet")
    pl.DataFrame([{"bidder_id": "b1", "canonical_name": "A", "variants": '["A"]', "n_awards": 1,
                   "total_value_crore": 0.5, "first_award": "2026-09-01", "last_award": "2026-09-01"}]).write_parquet(root / "clean" / "bidders.parquet")
    pl.DataFrame([{"pe_id": "p1", "name": "PE", "ministry": "M", "n_contracts": 1, "n_tenders": 3}]).write_parquet(root / "clean" / "procuring_entities.parquet")


def test_plan_selects_window_escapes_and_caps(tmp_path: Path):
    _clean(tmp_path)
    plan = d1.plan_load(tmp_path, d1.Watermark(), max_rows=100, today="2026-09-13")
    sql = "\n".join(plan.statements)
    assert "INSERT OR REPLACE INTO tenders" in sql and "'O''Brien supply'" in sql
    assert "'Old one'" not in sql                                   # outside the 12 month window
    assert "INSERT OR REPLACE INTO contracts" in sql and "INSERT OR REPLACE INTO bidders" in sql
    assert plan.rows == 2 + 1 + 1 + 1
    assert plan.watermark.tenders == "20260913T070000000002Z" and plan.watermark.contracts == "20260913T070000000003Z"


def test_cap_stops_and_watermark_resumes(tmp_path: Path):
    _clean(tmp_path)
    first = d1.plan_load(tmp_path, d1.Watermark(), max_rows=1, today="2026-09-13")
    assert first.rows == 1 and first.watermark.tenders == "20260913T070000000000Z"
    second = d1.plan_load(tmp_path, first.watermark, max_rows=100, today="2026-09-13")
    assert "'Newer'" in "\n".join(second.statements) and "'O''Brien supply'" not in "\n".join(second.statements)


def test_statements_are_batched(tmp_path: Path):
    (tmp_path / "clean").mkdir()
    rows = [{"tender_id": str(i), "title": f"t{i}", "fetched_at": f"2026091{i % 10}", "published_at": "2026-09-01T00:00",
             "status": "Live"} for i in range(1200)]
    pl.DataFrame(rows).write_parquet(tmp_path / "clean" / "tenders.parquet")
    plan = d1.plan_load(tmp_path, d1.Watermark(), max_rows=5000, today="2026-09-13")
    tender_stmts = [s for s in plan.statements if s.startswith("INSERT OR REPLACE INTO tenders")]
    assert len(tender_stmts) == 3 and plan.rows == 1200


def test_watermark_roundtrip(tmp_path: Path):
    w = d1.Watermark(tenders="a", contracts="b", loaded_rows_today=5, day="2026-09-13")
    w.save(tmp_path / "w.json")
    assert d1.Watermark.load(tmp_path / "w.json") == w
    assert d1.Watermark.load(tmp_path / "missing.json") == d1.Watermark()


def test_write_sql_files(tmp_path: Path):
    _clean(tmp_path)
    plan = d1.plan_load(tmp_path, d1.Watermark(), max_rows=100, today="2026-09-13")
    files = d1.write_sql(plan, tmp_path / "build", statements_per_file=2)
    assert len(files) == -(-len(plan.statements) // 2)
    assert files[0].read_text(encoding="utf-8").count("INSERT OR REPLACE") == 2
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/test_d1_export.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bidefy.export'`

- [ ] **Step 4: Write the exporter**

`bidefy/export/__init__.py`:
```python
"""Load clean tables into Cloudflare D1 within the free tier's daily write budget."""
```

`bidefy/export/d1.py`:
```python
"""Plan and execute capped, resumable loads from data/clean into D1 through wrangler."""
from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path

import polars as pl

WINDOW_MONTHS = 12
BATCH_ROWS = 500
DEFAULT_MAX_ROWS = 90_000
TABLES = {
    "tenders": ["tender_id", "reference", "status", "note", "nature", "title", "ministry", "organization",
                "procuring_entity", "pe_id", "procurement_type", "method", "published_at", "closing_at", "fetched_at"],
    "contracts": ["tender_id", "reference", "title", "advertised_at", "ministry", "procuring_entity", "pe_id",
                  "method", "district", "signed_on", "awardee", "bidder_id", "value_crore", "fetched_at"],
    "bidders": ["bidder_id", "canonical_name", "variants", "n_awards", "total_value_crore", "first_award", "last_award"],
    "procuring_entities": ["pe_id", "name", "ministry", "n_contracts", "n_tenders"],
}


@dataclass
class Watermark:
    tenders: str = ""
    contracts: str = ""
    loaded_rows_today: int = 0
    day: str = ""

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)

    @classmethod
    def load(cls, path: Path) -> "Watermark":
        if not Path(path).exists():
            return cls()
        return cls(**json.loads(Path(path).read_text(encoding="utf-8")))


@dataclass
class Plan:
    statements: list[str] = field(default_factory=list)
    rows: int = 0
    watermark: Watermark = field(default_factory=Watermark)


def _sql_value(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float)):
        return repr(v)
    return "'" + str(v).replace("'", "''") + "'"


def _inserts(table: str, df: pl.DataFrame) -> list[str]:
    cols = [c for c in TABLES[table] if c in df.columns]
    out = []
    rows = df.select(cols).rows()
    for i in range(0, len(rows), BATCH_ROWS):
        values = ",\n".join("(" + ", ".join(_sql_value(v) for v in row) + ")" for row in rows[i:i + BATCH_ROWS])
        out.append(f"INSERT OR REPLACE INTO {table} ({', '.join(cols)}) VALUES\n{values};")
    return out


def _read(root: Path, name: str) -> pl.DataFrame:
    path = Path(root) / "clean" / f"{name}.parquet"
    return pl.read_parquet(path) if path.exists() else pl.DataFrame()


def plan_load(root: Path, watermark: Watermark, max_rows: int = DEFAULT_MAX_ROWS, today: str | None = None) -> Plan:
    """Recent tenders and contracts newer than the watermark (by fetched_at), then all bidders and entities."""
    today_d = date.fromisoformat(today) if today else date.today()
    window_start = (today_d - timedelta(days=30 * WINDOW_MONTHS)).isoformat()
    plan = Plan(watermark=Watermark(tenders=watermark.tenders, contracts=watermark.contracts, day=today_d.isoformat()))
    budget = max_rows

    for table, date_col in (("tenders", "published_at"), ("contracts", "signed_on")):
        df = _read(root, table)
        if df.is_empty() or budget <= 0:
            continue
        if "fetched_at" not in df.columns:
            df = df.with_columns(pl.lit("").alias("fetched_at"))
        mark = getattr(watermark, table)
        recent = df.filter(pl.col(date_col).fill_null("") >= window_start) if date_col in df.columns else df
        if table == "tenders" and "status" in df.columns:
            recent = pl.concat([recent, df.filter(pl.col("status") == "Live")]).unique(subset=["tender_id"], keep="last")
        pending = recent.filter(pl.col("fetched_at").cast(pl.Utf8) > mark).sort("fetched_at")
        take = pending.head(budget)
        if take.is_empty():
            continue
        plan.statements += _inserts(table, take)
        plan.rows += take.height
        budget -= take.height
        setattr(plan.watermark, table, str(take["fetched_at"][-1]))

    for table in ("bidders", "procuring_entities"):
        df = _read(root, table)
        if df.is_empty() or budget <= 0:
            continue
        take = df.head(budget)
        plan.statements += _inserts(table, take)
        plan.rows += take.height
        budget -= take.height
    plan.watermark.loaded_rows_today = plan.rows
    return plan


def write_sql(plan: Plan, out_dir: Path, statements_per_file: int = 20) -> list[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("batch-*.sql"):
        old.unlink()
    files = []
    for i in range(0, len(plan.statements), statements_per_file):
        path = out_dir / f"batch-{i // statements_per_file:04d}.sql"
        path.write_text("\n".join(plan.statements[i:i + statements_per_file]) + "\n", encoding="utf-8")
        files.append(path)
    return files


def execute(files: list[Path], database: str, remote: bool, runner=subprocess.run) -> None:
    for path in files:
        cmd = ["npx", "wrangler", "d1", "execute", database, "--remote" if remote else "--local", "--file", str(path), "--yes"]
        result = runner(cmd, cwd="worker", shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"wrangler failed on {path.name}: {result.stderr[-2000:]}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Load clean tables into D1 within the daily write cap")
    ap.add_argument("--data-root", default="data")
    ap.add_argument("--watermark", default="checkpoints/d1_load.json")
    ap.add_argument("--max-rows", type=int, default=DEFAULT_MAX_ROWS)
    ap.add_argument("--database", default="bidefy")
    ap.add_argument("--local", action="store_true", help="load the local wrangler D1 instead of remote")
    ap.add_argument("--dry-run", action="store_true", help="write SQL files, do not execute")
    a = ap.parse_args(argv)
    wm = Watermark.load(Path(a.watermark))
    plan = plan_load(Path(a.data_root), wm, max_rows=a.max_rows)
    files = write_sql(plan, Path("build") / "d1")
    print(f"d1 load: {plan.rows} rows in {len(plan.statements)} statements across {len(files)} files")
    if a.dry_run or not files:
        return 0
    execute(files, a.database, remote=not a.local)
    plan.watermark.save(Path(a.watermark))
    print(f"d1 load: done, watermark tenders={plan.watermark.tenders} contracts={plan.watermark.contracts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_d1_export.py -v`
Expected: 5 passed

- [ ] **Step 6: Add build/ to .gitignore and commit**

Append `build/` to `.gitignore`, then:
```bash
git add worker/schema.sql bidefy/export tests/test_d1_export.py .gitignore
git commit -m "Add D1 schema and capped resumable loader"
```

---

### Task 6: Worker API on workers.dev

A Hono Worker bound to D1. Query builders are pure functions in `query.ts` so vitest can test them without a D1 instance. Routes return JSON only; the Vercel frontend consumes them in week 3, so CORS is open for GET.

**Files:**
- Create: `worker/package.json`, `worker/tsconfig.json`, `worker/wrangler.jsonc`
- Create: `worker/src/query.ts`, `worker/src/index.ts`
- Create: `worker/test/query.test.ts`

- [ ] **Step 1: Write the project files**

`worker/package.json`:
```json
{
  "name": "bidefy-worker",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "wrangler dev",
    "deploy": "wrangler deploy",
    "test": "vitest run",
    "schema:remote": "wrangler d1 execute bidefy --remote --file schema.sql --yes",
    "schema:local": "wrangler d1 execute bidefy --local --file schema.sql --yes"
  },
  "dependencies": {
    "hono": "^4.6.0"
  },
  "devDependencies": {
    "@cloudflare/workers-types": "^4.20250101.0",
    "typescript": "^5.6.0",
    "vitest": "^2.1.0",
    "wrangler": "^4.0.0"
  }
}
```

`worker/tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ES2022",
    "moduleResolution": "Bundler",
    "strict": true,
    "types": ["@cloudflare/workers-types"],
    "noEmit": true,
    "skipLibCheck": true
  },
  "include": ["src", "test"]
}
```

`worker/wrangler.jsonc`:
```jsonc
{
  "$schema": "node_modules/wrangler/config-schema.json",
  "name": "bidefy",
  "main": "src/index.ts",
  "compatibility_date": "2026-09-01",
  "workers_dev": true,
  "observability": { "enabled": true },
  "d1_databases": [
    { "binding": "DB", "database_name": "bidefy", "database_id": "9a19c0e9-6e01-4066-8615-8eee5267ce2c" }
  ],
  "triggers": { "crons": ["0 * * * *"] }
}
```

- [ ] **Step 2: Write the failing query tests**

`worker/test/query.test.ts`:
```ts
import { describe, expect, it } from "vitest";
import { parseTenderFilters, tenderListQuery, tenderByIdQuery, bidderQuery, peQuery } from "../src/query";

describe("parseTenderFilters", () => {
  it("defaults and clamps", () => {
    const f = parseTenderFilters(new URLSearchParams(""));
    expect(f).toEqual({ q: "", status: "Live", ministry: "", district: "", page: 1, size: 25 });
    const g = parseTenderFilters(new URLSearchParams("status=all&page=0&size=999&q=%20printer%20"));
    expect(g.status).toBe("all");
    expect(g.page).toBe(1);
    expect(g.size).toBe(100);
    expect(g.q).toBe("printer");
  });
});

describe("tenderListQuery", () => {
  it("builds a parameterised query with filters and paging", () => {
    const { sql, params } = tenderListQuery({ q: "printer", status: "Live", ministry: "Ministry of Finance", district: "", page: 3, size: 25 });
    expect(sql).toContain("FROM tenders");
    expect(sql).toContain("status = ?");
    expect(sql).toContain("title LIKE ?");
    expect(sql).toContain("ministry = ?");
    expect(sql).toContain("ORDER BY published_at DESC");
    expect(sql).toContain("LIMIT ? OFFSET ?");
    expect(params).toEqual(["Live", "%printer%", "Ministry of Finance", 25, 50]);
  });
  it("omits the status clause for all", () => {
    const { sql, params } = tenderListQuery({ q: "", status: "all", ministry: "", district: "", page: 1, size: 10 });
    expect(sql).not.toContain("status = ?");
    expect(params).toEqual([10, 0]);
  });
});

describe("detail queries", () => {
  it("tender by id joins the contract", () => {
    const q = tenderByIdQuery("123");
    expect(q.sql).toContain("LEFT JOIN contracts");
    expect(q.params).toEqual(["123"]);
  });
  it("bidder and pe queries take one id", () => {
    expect(bidderQuery("b1").params).toEqual(["b1"]);
    expect(peQuery("p1").params).toEqual(["p1"]);
  });
});
```

- [ ] **Step 3: Install and run to verify failure**

Run: `cd C:/Users/hp/Auto/egp-intel/worker && npm install && npx vitest run`
Expected: install succeeds; vitest FAILS with `Failed to resolve import "../src/query"`.

- [ ] **Step 4: Write query.ts**

`worker/src/query.ts`:
```ts
export type TenderFilters = { q: string; status: string; ministry: string; district: string; page: number; size: number };
export type Query = { sql: string; params: (string | number)[] };

const MAX_SIZE = 100;

export function parseTenderFilters(sp: URLSearchParams): TenderFilters {
  const page = Math.max(1, Number.parseInt(sp.get("page") ?? "1", 10) || 1);
  const size = Math.min(MAX_SIZE, Math.max(1, Number.parseInt(sp.get("size") ?? "25", 10) || 25));
  return {
    q: (sp.get("q") ?? "").trim(),
    status: (sp.get("status") ?? "Live").trim() || "Live",
    ministry: (sp.get("ministry") ?? "").trim(),
    district: (sp.get("district") ?? "").trim(),
    page,
    size,
  };
}

export function tenderListQuery(f: TenderFilters): Query {
  const where: string[] = [];
  const params: (string | number)[] = [];
  if (f.status !== "all") { where.push("status = ?"); params.push(f.status); }
  if (f.q) { where.push("title LIKE ?"); params.push(`%${f.q}%`); }
  if (f.ministry) { where.push("ministry = ?"); params.push(f.ministry); }
  const sql =
    "SELECT tender_id, reference, status, nature, title, ministry, organization, procuring_entity, pe_id, method, published_at, closing_at " +
    "FROM tenders" + (where.length ? " WHERE " + where.join(" AND ") : "") +
    " ORDER BY published_at DESC LIMIT ? OFFSET ?";
  params.push(f.size, (f.page - 1) * f.size);
  return { sql, params };
}

export function tenderByIdQuery(id: string): Query {
  return {
    sql:
      "SELECT t.*, c.awardee, c.bidder_id, c.value_crore, c.signed_on, c.district " +
      "FROM tenders t LEFT JOIN contracts c ON c.tender_id = t.tender_id WHERE t.tender_id = ?",
    params: [id],
  };
}

export function similarAwardsQuery(peId: string): Query {
  return {
    sql: "SELECT tender_id, title, awardee, bidder_id, value_crore, signed_on FROM contracts WHERE pe_id = ? ORDER BY signed_on DESC LIMIT 10",
    params: [peId],
  };
}

export function bidderQuery(id: string): Query {
  return { sql: "SELECT * FROM bidders WHERE bidder_id = ?", params: [id] };
}

export function bidderAwardsQuery(id: string): Query {
  return {
    sql: "SELECT tender_id, title, procuring_entity, pe_id, district, value_crore, signed_on FROM contracts WHERE bidder_id = ? ORDER BY signed_on DESC LIMIT 50",
    params: [id],
  };
}

export function peQuery(id: string): Query {
  return { sql: "SELECT * FROM procuring_entities WHERE pe_id = ?", params: [id] };
}

export function peTopBiddersQuery(id: string): Query {
  return {
    sql:
      "SELECT bidder_id, awardee, COUNT(*) AS n_awards, SUM(COALESCE(value_crore, 0)) AS total_value_crore " +
      "FROM contracts WHERE pe_id = ? AND bidder_id != '' GROUP BY bidder_id, awardee ORDER BY n_awards DESC LIMIT 10",
    params: [id],
  };
}
```

- [ ] **Step 5: Write index.ts**

`worker/src/index.ts`:
```ts
import { Hono } from "hono";
import { cors } from "hono/cors";
import {
  bidderAwardsQuery, bidderQuery, parseTenderFilters, peQuery, peTopBiddersQuery,
  similarAwardsQuery, tenderByIdQuery, tenderListQuery,
} from "./query";

type Bindings = { DB: D1Database };
const app = new Hono<{ Bindings: Bindings }>();

app.use("/api/*", cors({ origin: "*", allowMethods: ["GET", "OPTIONS"] }));

app.get("/", (c) => c.json({ name: "Bidefy API", docs: "/api/v1/health" }));

app.get("/api/v1/health", async (c) => {
  const counts = await c.env.DB.batch([
    c.env.DB.prepare("SELECT COUNT(*) AS n FROM tenders"),
    c.env.DB.prepare("SELECT COUNT(*) AS n FROM contracts"),
    c.env.DB.prepare("SELECT COUNT(*) AS n FROM bidders"),
    c.env.DB.prepare("SELECT MAX(published_at) AS newest FROM tenders"),
  ]);
  const n = (i: number) => (counts[i].results?.[0] as Record<string, unknown> | undefined) ?? {};
  return c.json({ ok: true, tenders: n(0).n ?? 0, contracts: n(1).n ?? 0, bidders: n(2).n ?? 0, newest_tender: n(3).newest ?? null });
});

app.get("/api/v1/tenders", async (c) => {
  const f = parseTenderFilters(new URL(c.req.url).searchParams);
  const q = tenderListQuery(f);
  const { results } = await c.env.DB.prepare(q.sql).bind(...q.params).all();
  return c.json({ page: f.page, size: f.size, items: results ?? [] });
});

app.get("/api/v1/tenders/:id", async (c) => {
  const id = c.req.param("id");
  const q = tenderByIdQuery(id);
  const tender = await c.env.DB.prepare(q.sql).bind(...q.params).first();
  if (!tender) return c.json({ error: "not found" }, 404);
  const s = similarAwardsQuery(String((tender as Record<string, unknown>).pe_id ?? ""));
  const { results } = await c.env.DB.prepare(s.sql).bind(...s.params).all();
  return c.json({ tender, similar_awards: results ?? [] });
});

app.get("/api/v1/bidders/:id", async (c) => {
  const id = c.req.param("id");
  const b = bidderQuery(id);
  const bidder = await c.env.DB.prepare(b.sql).bind(...b.params).first();
  if (!bidder) return c.json({ error: "not found" }, 404);
  const a = bidderAwardsQuery(id);
  const { results } = await c.env.DB.prepare(a.sql).bind(...a.params).all();
  return c.json({ bidder, awards: results ?? [] });
});

app.get("/api/v1/pe/:id", async (c) => {
  const id = c.req.param("id");
  const p = peQuery(id);
  const pe = await c.env.DB.prepare(p.sql).bind(...p.params).first();
  if (!pe) return c.json({ error: "not found" }, 404);
  const t = peTopBiddersQuery(id);
  const { results } = await c.env.DB.prepare(t.sql).bind(...t.params).all();
  return c.json({ procuring_entity: pe, top_bidders: results ?? [] });
});

export default {
  fetch: app.fetch,
  async scheduled(_event: ScheduledEvent, env: Bindings, _ctx: ExecutionContext) {
    // Week 4 wires the alert matcher here. For now record the tick so the cron is observable.
    await env.DB.prepare("INSERT OR REPLACE INTO meta (key, value) VALUES ('last_cron', ?)").bind(new Date().toISOString()).run();
  },
};
```

- [ ] **Step 6: Run the unit tests and a type check**

Run: `cd C:/Users/hp/Auto/egp-intel/worker && npx vitest run && npx tsc -p tsconfig.json`
Expected: vitest `6 passed`; tsc prints nothing.

- [ ] **Step 7: Apply the schema and deploy**

Run: `cd C:/Users/hp/Auto/egp-intel/worker && npm run schema:remote && npx wrangler deploy`
Expected: schema applies (7 tables, 8 indexes reported as executed), and deploy prints a URL of the form `https://bidefy.<subdomain>.workers.dev`. Record that URL.

- [ ] **Step 8: First load into D1 and smoke test**

Run: `cd C:/Users/hp/Auto/egp-intel && uv run python -m bidefy.export.d1 --max-rows 20000`
Expected: `d1 load: N rows in M statements across K files` then `d1 load: done, watermark ...`, and `checkpoints/d1_load.json` written.

Run: `curl -s https://bidefy.<subdomain>.workers.dev/api/v1/health; echo; curl -s "https://bidefy.<subdomain>.workers.dev/api/v1/tenders?q=printer&size=2"`
Expected: health JSON with tenders greater than 0, and a JSON list with items.

- [ ] **Step 9: Add worker ignores and commit**

Append to `.gitignore`: `worker/node_modules/` and `worker/.wrangler/`. Then:
```bash
git add worker .gitignore checkpoints/d1_load.json
git commit -m "Add Worker API on D1 with query builders and first load"
git pull --rebase
git push
```

---

### Task 7: Status, docs and README

**Files:**
- Modify: `status.yaml`, `README.md`
- Create: `docs/product/01-market.md`

- [ ] **Step 1: Write the market section**

`docs/product/01-market.md`:
```markdown
# Market and competition

## Who pays for tender information today

Bangladesh's e-GP portal publishes every public tender notice and contract award without a login. Around it sits a small industry of alert services that re-sell the notices.

| Service | What it sells | Price |
|---|---|---|
| BDTender | Daily notices by category, district and organisation over email and WhatsApp, plus e-GP training | 1,050 taka a month, 8,190 a year, 9,999 premium |
| AllTender | Notices from newspapers, websites and e-GP | Subscription |
| Global aggregators | Bangladesh notices bundled into a world feed | Foreign-currency subscriptions |

None of them use the contract award data. None can say who wins at a given entity, at what value, or how often. That is the layer Bidefy sells.

## The buyers

- **Contractors and suppliers bidding on multi-crore tenders.** One better-priced bid pays for years of subscription. They already pay the alert services.
- **Companies selling to government**, including large groups with tender desks.
- **Banks and lenders** that finance contractors against awarded contracts and need a verified award history.
- **Journalists and researchers**, who use the free tier and spread the product.

## Why not compete on alerts

The alert market has an anchor at about 1,050 taka a month and a lifetime-licence mentality. Bidefy gives the alert layer away and prices the intelligence layer against the value of one contract, not against a competitor's feature table.

## What the portal does not publish

Losing bids, bidder counts and official cost estimates are not public. Bidefy predicts award value bands from the security amount, the entity's history and the category, and reports an interval with a deferral rate rather than a point.
```

- [ ] **Step 2: Update status.yaml and README**

In `status.yaml` set `w2-contracts` to `doing` (the backfill runs across nights), and `w2-resolve`, `w2-d1`, `w2-worker` to `done`. Add under `w2`:
```yaml
      - {id: w2-api-live, title: "Worker API live on workers.dev", owner: claude, state: done, weight: 1, note: "<the deployed URL>"}
```
In `README.md` add a section:
```markdown
## Worker API

Live at `https://bidefy.<subdomain>.workers.dev` (replace with the deployed URL). Routes: `/api/v1/health`, `/api/v1/tenders?q=&status=&ministry=&page=&size=`, `/api/v1/tenders/:id`, `/api/v1/bidders/:id`, `/api/v1/pe/:id`.

```bash
cd worker && npm install && npm test
npm run schema:remote          # once
npx wrangler deploy
cd .. && uv run python -m bidefy.export.d1 --max-rows 90000   # nightly-sized load
```
```

- [ ] **Step 3: Commit and push**

```bash
git add docs/product/01-market.md status.yaml README.md
git commit -m "Add market section, week 2 status, API docs"
git pull --rebase
git push
```

---

## Self-review against the spec

- 5.2 normalize: Tasks 2 to 4 cover normalisation, blocking, TF-IDF similarity, thresholds 0.92 and 0.80, review CSV, stable ids, clean Parquet. Procuring entities are resolved by normalised name only, which the spec calls "cleaner"; a similarity pass for them can follow if the data shows variants.
- 5.4 export and load: Task 5 covers the 100,000 daily write cap through `--max-rows`, the 12 month window, live tenders regardless of age, the watermark, wrangler execution. The nightly Actions execution needs the API token, listed as Fahim's task; until then the loader runs locally.
- 5.5 worker: Task 6 covers the API routes for tenders, one tender with similar awards, bidder and entity profiles, the D1 binding, an hourly cron stub, CORS for the future Vercel frontend. Pages, PWA, subscriptions and push are weeks 3 and 4.
- Testing: pytest for names, resolve, build, d1 export; vitest for query builders; tsc type check.
- Names consistent across tasks: `normalize_name`, `block_key`, `resolve`, `Resolution`, `read_review`, `write_review`, `entity_id`, `build`, `Watermark`, `Plan`, `plan_load`, `write_sql`, `execute`, `parseTenderFilters`, `tenderListQuery`, `tenderByIdQuery`, `similarAwardsQuery`, `bidderQuery`, `bidderAwardsQuery`, `peQuery`, `peTopBiddersQuery`.
