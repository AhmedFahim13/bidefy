"""Categories read from the portal's CPV codes through the official code hierarchy.

The e-GP detail page lists a tender's procurement categories as plain CPV descriptions, such as
"Site preparation work" or "Electric motors, generators and transformers". Those descriptions
match the European Commission's Common Procurement Vocabulary word for word, so each one can be
turned back into its official eight-digit code and read through the hierarchy the code encodes.
The official list lives in data/cpv_2008.csv, fetched from the EU Publications Office.

This replaces a keyword labeller that matched substrings of the descriptions. That labeller let
"Site preparation work" vote for food ("ration"), "carpentry" vote for vehicles ("car") and
office supplies ("pen"), and "vegetables" vote for furniture ("table"). The model was being
trained and scored against those votes.

Two facts about the data shape this module.

First, most buyers tick a whole CPV division rather than a code within it, and the portal then
lists every group beneath. 77 percent of construction tenders carry all 26 construction groups.
For those, the tags say "construction" and nothing about roads, buildings or water. So a label
has two levels: the sector, which the tags nearly always support, and the sub-type, which they
support only when the buyer named something specific. Where they do not, the sub-type is left
empty rather than guessed.

Second, the portal mixes CPV 2008 wording with some older CPV 2003 descriptions. The commonest
of those are mapped to their 2008 codes below; anything still unrecognised is ignored, never
guessed.
"""
from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

CPV_FILE = Path(__file__).with_name("data") / "cpv_2008.csv"

CONSTRUCTION = ("roads_bridges", "buildings_civil", "water_sanitation")
EXPANDED_SHARE = 0.6        # ticking this share of a division's groups means the division was picked
MIN_GROUPS_TO_EXPAND = 5    # a division this small cannot be told apart from a specific choice
SILENT = "silent"           # a code that says nothing, not even its division's sector

# Longest matching prefix wins. None means the code says nothing reliable about the category.
PREFIX_CATEGORY: dict[str, str | None] = {
    "03": "agriculture_environment",
    "091": "vehicles_transport", "093": "electrical_power",
    "142": "buildings_civil",
    "15": "food_catering",
    "16": "agriculture_environment",
    "18": "textiles_uniforms", "185": SILENT,
    "19": "textiles_uniforms", "195": SILENT, "196": SILENT, "197": SILENT,
    "22": "printing_media",
    "244": "agriculture_environment",
    "30": "office_supplies", "3012": "it_equipment", "302": "it_equipment",
    "31": "electrical_power",
    "32": "it_equipment",
    "33": "medical", "337": SILENT, "3373": "medical",
    "34": "vehicles_transport",
    "35": "security_cleaning_services", "354": "vehicles_transport", "358": "textiles_uniforms",
    "37": None,
    "38": None, "3843": "medical", "3851": "medical",
    "39": None, "391": "furniture", "3919": "buildings_civil", "3931": "food_catering",
    "395": "textiles_uniforms", "397": "electrical_power", "398": "security_cleaning_services",
    "41": "water_sanitation",
    "42": None, "4211": "electrical_power", "4212": "water_sanitation", "4213": "water_sanitation",
    "425": "electrical_power",
    "43": None,
    "44": "buildings_civil", "44113": "roads_bridges", "4413": "water_sanitation",
    "4416": "water_sanitation", "443": "electrical_power", "4461": "water_sanitation",
    "45": None,
    "4521": "buildings_civil", "45221": "roads_bridges",
    "45231": None, "452313": "water_sanitation", "452314": "electrical_power", "452316": "it_equipment",
    "45232": "water_sanitation", "45233": "roads_bridges", "45234": "roads_bridges",
    "45235": "roads_bridges", "45236": "buildings_civil",
    "4524": "water_sanitation",
    "4525": "buildings_civil", "45251": "electrical_power", "45252": "water_sanitation",
    "4526": "buildings_civil",
    "4531": "electrical_power", "4532": "buildings_civil", "4533": "water_sanitation",
    "4534": "buildings_civil", "4535": "buildings_civil",
    "454": "buildings_civil",
    "48": "it_equipment",
    "50": None, "501": "vehicles_transport", "5023": "roads_bridges", "5024": "vehicles_transport",
    "503": "it_equipment", "504": "medical", "505": "water_sanitation", "5053": None,
    "5071": "electrical_power", "5072": "buildings_civil", "5073": "electrical_power",
    "5074": "buildings_civil", "5075": "buildings_civil", "5083": "textiles_uniforms", "5085": "furniture",
    "51": None, "511": "electrical_power", "513": "it_equipment", "514": "medical", "516": "it_equipment",
    "55": "food_catering",
    "60": "vehicles_transport",
    "63": "vehicles_transport",
    "642": "it_equipment",
    "651": "water_sanitation", "653": "electrical_power",
    "66": "consultancy",
    "71": "consultancy",
    "72": "it_equipment",
    "73": "consultancy",
    "77": "agriculture_environment",
    "79": None, "791": "consultancy", "792": "consultancy", "793": "consultancy", "7934": "printing_media",
    "794": "consultancy", "796": "security_cleaning_services", "797": "security_cleaning_services",
    "798": "printing_media", "7997": "printing_media", "7998": "printing_media",
    "80": "consultancy",
    "85": "medical",
    "904": "water_sanitation", "905": "security_cleaning_services", "906": "security_cleaning_services",
    "907": "agriculture_environment", "909": "security_cleaning_services",
    "921": "printing_media", "922": "printing_media",
    "9831": "security_cleaning_services",
}

# The sector a whole division belongs to, used when a buyer ticked the entire division. Divisions
# that span several sectors, such as repair services or machinery, are deliberately absent.
DIVISION_SECTOR: dict[str, str] = {
    "03": "agriculture_environment", "15": "food_catering", "16": "agriculture_environment",
    "18": "textiles_uniforms", "19": "textiles_uniforms", "22": "printing_media",
    "31": "electrical_power", "32": "it_equipment", "33": "medical", "34": "vehicles_transport",
    "35": "security_cleaning_services", "41": "water_sanitation", "44": "construction",
    "45": "construction", "48": "it_equipment", "55": "food_catering", "60": "vehicles_transport",
    "63": "vehicles_transport", "66": "consultancy", "71": "consultancy", "72": "it_equipment",
    "73": "consultancy", "77": "agriculture_environment", "80": "consultancy", "85": "medical",
}

# CPV 2003 wording still used by the portal, mapped to the CPV 2008 code that replaced it.
LEGACY_ALIASES: dict[str, str] = {
    "construction work for pipelines, communication and power lines, for highways, roads, airfields and railways": "45230000",
    "repair, maintenance and installation services": "50000000",
    "installation services": "51000000",
    "electrical machinery, apparatus, equipment and consumables": "31000000",
    "medical and laboratory devices, optical and precision devices, watches and clocks": "33000000",
    "medical and laboratory devices, optical and precision devices, watches and clocks, pharmaceuticals and related medical consumables": "33000000",
    "medical devices": "33100000",
    "medical non-chemical consumables and haematological consumables": "33141000",
    "miscellaneous medical devices": "33190000",
    "dentistry": "33130000",
    "therapy": "33150000",
    "functional exploration": "33120000",
    "food products and beverages": "15000000",
    "fruit and vegetables": "15300000",
    "miscellaneous food products n.e.c. and dried goods": "15800000",
    "rusks and biscuits": "15820000",
    "preserved pastry goods and cakes": "15820000",
    "dried or salted fish": "15230000",
    "beverages": "15900000",
    "office machinery, equipment and supplies except computers": "30100000",
    "office and computing machinery, equipment and supplies": "30000000",
    "computer hardware": "30230000",
    "computer systems": "30210000",
    "data-processing machines": "30210000",
    "photocopying and printing equipment": "30120000",
    "software": "48000000",
    "agricultural, horticultural and forestry machinery": "16000000",
    "transport related equipment": "34000000",
    "spectacles and lenses": "33734000",
    "truncheons or night sticks": "35300000",
    "parts of military weapons": "35300000",
    "military weapons": "35300000",
    "motorised tanks and armoured fighting vehicles": "35400000",
}

SECTORS = sorted({("construction" if c in CONSTRUCTION else c) for c in PREFIX_CATEGORY.values() if c}
                 | set(DIVISION_SECTOR.values()))


def sector_of(category: str | None) -> str | None:
    if not category:
        return None
    return "construction" if category in CONSTRUCTION else category


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower()).rstrip(".")


@lru_cache(maxsize=1)
def _table() -> tuple[dict[str, str], dict[str, int]]:
    """Official label to code, and how many groups each division has."""
    by_label: dict[str, str] = {}
    groups: dict[str, set[str]] = defaultdict(set)
    with open(CPV_FILE, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            code, label = row["code"], row["label"]
            by_label[_norm(label)] = code
            by_label.setdefault(_norm(label.split(";")[0]), code)
            groups[code[:2]].add(code[:4])
    for label, code in LEGACY_ALIASES.items():
        by_label.setdefault(_norm(label), code)
    return by_label, {d: len(g) for d, g in groups.items()}


def code_for(tag: str) -> str | None:
    return _table()[0].get(_norm(tag))


_UNMAPPED = object()

# Older CPV divisions that the 2008 edition split across several new ones. A buyer who ticks one of
# these whole gets every descendant listed, so none of those codes says what the tender is for. The
# manufactured-goods division is the clear case: of 983 tenders carrying it, 519 were furniture and
# 431 were other household and general goods, so it cannot be read as furniture.
LEGACY_DIVISION_PICKS: dict[str, tuple[str, ...]] = {
    "manufactured goods, furniture, handicrafts": ("0334", "185", "352", "37", "391", "3923", "3929"),
}


def _lookup(code: str):
    """The mapped category, None where a code is deliberately uninformative, or _UNMAPPED."""
    for size in range(len(code), 1, -1):
        prefix = code[:size]
        if prefix in PREFIX_CATEGORY:
            return PREFIX_CATEGORY[prefix]
    return _UNMAPPED


def category_for_code(code: str) -> str | None:
    found = _lookup(code)
    return None if found is _UNMAPPED or found == SILENT else found


@dataclass(frozen=True)
class CpvLabel:
    sector: str | None       # nearly always supported by the tags
    category: str | None     # the fine category, only where the tags actually name it
    margin: int              # how decisively the sector won
    codes: int               # recognised codes on the tender


def _winner(votes: Counter) -> tuple[str | None, int]:
    if not votes:
        return None, 0
    ranked = votes.most_common()
    top, count = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0
    if count == second or count / sum(votes.values()) < 0.5:
        return None, 0
    return top, count - second


def label(tags: list[str]) -> CpvLabel:
    """The sector and, where the buyer was specific, the fine category a tender's tags support."""
    codes = {c for c in (code_for(t) for t in tags if t) if c}
    if not codes:
        return CpvLabel(None, None, 0, 0)
    _, division_groups = _table()
    present: dict[str, set[str]] = defaultdict(set)
    for code in codes:
        present[code[:2]].add(code[:4])
    expanded = {d for d, gs in present.items()
                if division_groups.get(d, 0) >= MIN_GROUPS_TO_EXPAND
                and len(gs) / division_groups[d] >= EXPANDED_SHARE}
    # In the older CPV edition the portal still partly uses, repair (50) and installation (51) were
    # one division. A buyer who ticks it whole gets both lists. Treating the installation half as a
    # deliberate choice let computer installation outvote the rest, and 582 civil repair jobs came
    # out labelled as IT. A blind audit caught it.
    for pair in (("50", "51"), ("51", "50")):
        if pair[0] in expanded and pair[1] in present:
            expanded.add(pair[1])

    lowered = [_norm(t) for t in tags if t]
    silenced = tuple(p for root, prefixes in LEGACY_DIVISION_PICKS.items()
                     if any(t.startswith(root) for t in lowered) for p in prefixes)

    sector_votes: Counter = Counter()
    fine_votes: Counter = Counter()
    for code in codes:
        division = code[:2]
        if silenced and code.startswith(silenced):
            continue
        if division in expanded:
            if division in DIVISION_SECTOR:
                sector_votes[DIVISION_SECTOR[division]] += 1
            continue
        found = _lookup(code)
        if found == SILENT:
            continue       # jewellery inside clothing, say, must not vote for textiles
        # None means the sub-type is unknown, not the sector: a bare "Site preparation work" is
        # still construction, so it falls back to its division.
        category = None if found is _UNMAPPED else found
        sector = sector_of(category) or DIVISION_SECTOR.get(division)
        if sector:
            sector_votes[sector] += 1
        if category:
            fine_votes[category] += 1

    sector, margin = _winner(sector_votes)
    if not sector:
        return CpvLabel(None, None, 0, len(codes))
    if sector != "construction":
        return CpvLabel(sector, sector, margin, len(codes))
    # A construction division ticked whole hides whether the job is roads, buildings or water.
    if any(DIVISION_SECTOR.get(d) == "construction" for d in expanded):
        return CpvLabel(sector, None, margin, len(codes))
    fine, _ = _winner(Counter({c: n for c, n in fine_votes.items() if c in CONSTRUCTION}))
    return CpvLabel(sector, fine, margin, len(codes))
