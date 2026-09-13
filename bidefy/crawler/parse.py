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


def _label_map(rows: list[list[str]]) -> dict[str, str]:
    """Pairs 'Label :' cells with the cell to their right, across all rows.

    A label often spans several <br>-separated lines within one cell (e.g.
    "Tender/Proposal    Closing\nDate and Time :"), so the key is built by
    collapsing all whitespace, including embedded newlines, to single spaces.
    """
    out: dict[str, str] = {}
    for cells in rows:
        for i in range(len(cells) - 1):
            label = cells[i].strip()
            if label.endswith(":"):
                key = re.sub(r"\s+", " ", label.rstrip(":")).strip()
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
        # Lot rows have six cells: lot no. (a digit, or "single" for a
        # single-lot tender), description, entity, security amount, and two
        # dates.
        lot_no = cells[0].strip().lower() if cells else ""
        if len(cells) == 6 and (lot_no.isdigit() or lot_no == "single"):
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
        "published_at": parse_datetime(
            m.get("Scheduled Tender/Proposal Publication Date and Time", "")
        ),
        "closing_at": parse_datetime(
            m.get("Tender/Proposal Closing Date and Time", "")
        ),
        "document_price_bdt": _to_int(m.get("Tender/Proposal Document Price (In BDT)")),
        "security_bdt": security,
        "brief": m.get("Brief Description of Goods and Related Service", "") or m.get("Brief Description of Works", "") or m.get("Brief Description of Services", ""),
    }
