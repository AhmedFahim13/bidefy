"""Decide the borderline name pairs in review/pairs.csv that can be decided by rule.

The resolver merges names that look alike above 0.92 and queues everything from 0.80 to 0.92 for a
human. That queue holds tens of thousands of pairs, which no one will read. Most of them are
decidable without judgement, because the difference is only punctuation, an honorific such as Md,
or a legal suffix such as Ltd.

The rules, in order:

- Drop the noise. Honorifics (Md, Mst, Alhaj), legal suffixes (Ltd, Pvt, Co, Sons, Brothers) and
  punctuation carry no identity. Runs of single letters become one token, so "S. M." and "S.M"
  both read as "sm".
- Keep the trade word. "Kamal Enterprise" and "Kamal Construction" are not the same firm just
  because one owner's name appears in both, so Enterprise, Construction and the like stay in the
  name being compared.
- Merge when what is left is identical, or identical once reordered. "M/S Ma Baba Construction"
  and "MA-BABA CONSTRUCTION LTD." are one firm.
- Keep when what is left differs by a real token: different initials, a different trade word, or a
  different number. "S. M. Enterprise" and "S.S Enterprise" are two firms.
- Decide nothing else. Where one name simply carries an extra word, such as "Islam Enterprise" and
  "S.R Islam Enterprise", the rule abstains and the pair stays in the queue for a human.

Usage:
  uv run python tools/adjudicate_pairs.py --dry-run     # counts and samples, writes nothing
  uv run python tools/adjudicate_pairs.py               # writes decisions into review/pairs.csv
"""
from __future__ import annotations

import argparse
import csv
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bidefy.normalize.names import normalize_name  # noqa: E402

# "ms" only ever reaches here as a literal word, as in "Ms-Nayem Enterprise". Initials such as
# "M.S." arrive as two single letters and are joined after this filter, so they are never stripped.
HONORIFICS = {"ms", "md", "mohammad", "mohammed", "mohd", "muhammad", "mst", "most", "mosammat",
              "sree", "sri", "late", "engr", "engineer", "alhaj", "alhajj", "hajee", "haji", "dr",
              "prof", "mr", "mrs", "miss", "janab"}
LEGAL = {"ltd", "limited", "pvt", "private", "co", "company", "corporation", "corp", "inc",
         "and", "sons", "son", "bros", "brother", "brothers", "firm", "the"}
PLURALS = {"enterprises": "enterprise", "traders": "trader", "stores": "store", "suppliers": "supplier",
           "builders": "builder", "engineers": "engineer", "constructions": "construction",
           "industries": "industry", "agencies": "agency", "associates": "associate",
           "services": "service", "works": "work", "brickfields": "brickfield"}


def core(raw: str) -> tuple[str, ...]:
    """The identifying part of a name: no punctuation, honorifics or legal suffixes."""
    tokens = [PLURALS.get(t, t) for t in normalize_name(raw).split()]
    tokens = [t for t in tokens if t not in HONORIFICS and t not in LEGAL]
    out: list[str] = []
    initials: list[str] = []
    for token in tokens:
        if len(token) == 1:
            initials.append(token)
            continue
        if initials:
            out.append("".join(initials))
            initials = []
        out.append(token)
    if initials:
        out.append("".join(initials))
    return tuple(out)


def decide(a: str, b: str) -> str:
    """"merge", "keep", or "" when the pair needs a human."""
    ca, cb = core(a), core(b)
    if not ca or not cb:
        return ""
    if ca == cb or sorted(ca) == sorted(cb):
        return "merge"
    if set(ca) < set(cb) or set(cb) < set(ca):
        return ""                      # one name carries an extra word; a person must judge
    sa, sb = set(ca), set(cb)
    only_a, only_b = sa - sb, sb - sa
    if any(re.search(r"\d", t) for t in only_a | only_b):
        return "keep"                  # different numbers are different firms
    if len(only_a) == len(only_b) == 1:
        ta, tb = next(iter(only_a)), next(iter(only_b))
        if ta.startswith(tb) or tb.startswith(ta):
            return ""                  # an abbreviation of the other, or a truncated spelling
        return "keep"
    return "keep"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--review", default="review/pairs.csv")
    ap.add_argument("--dry-run", action="store_true", help="print counts and samples, write nothing")
    ap.add_argument("--samples", type=int, default=12)
    a = ap.parse_args(argv)

    path = ROOT / a.review
    rows = list(csv.DictReader(open(path, newline="", encoding="utf-8")))
    counts = {"merge": 0, "keep": 0, "": 0, "already": 0}
    decided: list[tuple[str, str, str]] = []
    undecided: list[tuple[str, str, str]] = []
    samples: dict[str, list[tuple[str, str]]] = {"merge": [], "keep": [], "": []}
    rng = random.Random(4)
    for row in rows:
        existing = (row.get("decision") or "").strip().lower()
        if existing in ("merge", "keep"):
            counts["already"] += 1
            decided.append((row["a"], row["b"], existing))
            continue
        verdict = decide(row["a"], row["b"])
        counts[verdict] += 1
        if len(samples[verdict]) < a.samples or rng.random() < 0.01:
            samples[verdict] = (samples[verdict] + [(row["a"], row["b"])])[-a.samples:]
        if verdict:
            decided.append((row["a"], row["b"], verdict))
        else:
            undecided.append((row["a"], row["b"], row.get("score") or ""))

    total = len(rows)
    print(f"{total:,} pairs: {counts['merge']:,} merge, {counts['keep']:,} keep, "
          f"{counts['']:,} left for a human, {counts['already']:,} already decided")
    for verdict, title in (("merge", "merged"), ("keep", "kept apart"), ("", "left for a human")):
        print(f"\n{title}:")
        for x, y in samples[verdict]:
            print(f"  {x!r:<44} {y!r}")
    if a.dry_run:
        return 0

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["a", "b", "score", "decision"])
        w.writerows([(x, y, "", d) for x, y, d in sorted(decided)])
        w.writerows([(x, y, s, "") for x, y, s in undecided])
    print(f"\nwrote {path}: {len(decided):,} decided rows, {len(undecided):,} still queued")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
