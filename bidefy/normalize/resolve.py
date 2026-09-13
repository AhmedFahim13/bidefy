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
    """Rewrite the CSV: decided rows first, then the current undecided pairs. Returns the row count."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [(a, b, "", d) for (a, b), d in sorted(existing.items())]
    rows += [(a, b, f"{s:.4f}", "") for a, b, s in pairs if _pair_key(a, b) not in existing]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["a", "b", "score", "decision"])
        w.writerows(rows)
    return len(rows)
