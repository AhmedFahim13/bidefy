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
        rest = title_lines[1:]
        # The advertisement date sits on the same line as the tail of the
        # title, with no <br> between them (observed in the real fixture:
        # the title text is wrapped in a <span class="more"> for CSS
        # truncation only, not a duplicate "more"/"less" line). Strip the
        # date (and anything after it) off the last line instead of
        # discarding the whole line.
        if rest:
            last = _DATE_RE.split(rest[-1])[0].strip()
            rest = rest[:-1] + ([last] if last else [])
        middle = [l for l in rest if l.lower() not in ("more", "less", "...")]
        title = " ".join(middle)
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
