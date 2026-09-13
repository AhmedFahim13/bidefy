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
