"""Fifteen Bidefy categories, and weak labels from the portal's own category tags or from titles."""
from __future__ import annotations

import re

CATEGORIES = [
    "roads_bridges", "buildings_civil", "water_sanitation", "electrical_power", "it_equipment",
    "office_supplies", "furniture", "medical", "vehicles_transport", "food_catering",
    "textiles_uniforms", "printing_media", "security_cleaning_services", "consultancy",
    "agriculture_environment",
]

LABELS = {
    "roads_bridges": "Roads and bridges",
    "buildings_civil": "Buildings and civil works",
    "water_sanitation": "Water and sanitation",
    "electrical_power": "Electrical and power",
    "it_equipment": "IT equipment and software",
    "office_supplies": "Office supplies",
    "furniture": "Furniture",
    "medical": "Medical and pharmaceutical",
    "vehicles_transport": "Vehicles and transport",
    "food_catering": "Food and catering",
    "textiles_uniforms": "Textiles and uniforms",
    "printing_media": "Printing and media",
    "security_cleaning_services": "Security and cleaning services",
    "consultancy": "Consultancy",
    "agriculture_environment": "Agriculture and environment",
}

# Keyword stems matched against the lowercased, space-joined tag text from the detail page.
# These name SUBJECTS, never actions. "Repair and maintenance" describes work done to a vehicle,
# a building or a pump alike, so including it made a vehicle-repair tender compete with itself
# and lose: the tag list resolved to no category at all. Nineteen percent of tagged tenders were
# being thrown away that way.
TAG_KEYWORDS: dict[str, list[str]] = {
    "roads_bridges": ["highway", "road", "bridge", "culvert", "pavement", "embankment", "bituminous",
                      "flyover", "footpath", "asphalt"],
    "buildings_civil": ["building", "brick", "cement", "concrete", "roofing", "plaster", "boundary wall",
                        "school building", "hostel", "structural", "wood", "timber", "sawn", "carpentry",
                        "tile", "glass", "paint", "sanitary ware", "construction material"],
    "water_sanitation": ["water supply", "sanitation", "sewer", "drain", "tube well", "pipe", "pump",
                         "latrine", "toilet", "water treatment", "irrigation", "water distribution"],
    "electrical_power": ["electric", "transformer", "cable", "generator", "solar", "substation",
                         "lighting", "conductor", "meter", "power distribution", "wiring", "switchgear",
                         "battery", "energy"],
    "it_equipment": ["computer", "software", "server", "laptop", "printer", "network", "hardware",
                     "data-processing", "data processing", "scanner", "photocopy", "ict",
                     "telecommunication", "camera", "information system"],
    "office_supplies": ["stationery", "office supplies", "paper", "toner", "pen", "envelope",
                        "office equipment", "office machinery", "consumable"],
    "furniture": ["furniture", "chair", "seat", "table", "almirah", "cabinet", "shelv", "bed", "sofa",
                  "desk", "handicraft"],
    "medical": ["medical", "pharmaceutical", "medicine", "medicinal", "drug", "hospital", "surgical",
                "laboratory", "reagent", "diagnostic", "vaccine", "dental", "x-ray", "health",
                "orthopaedic", "anaesthe"],
    "vehicles_transport": ["vehicle", "motor", "car", "bus", "truck", "ambulance", "motorcycle", "tyre",
                           "spare parts", "boat", "vessel", "transport services", "petroleum", "fuel",
                           "diesel", "lubricant", "oil and associated"],
    "food_catering": ["food", "rice", "catering", "meal", "ration", "beverage", "sugar", "flour",
                      "diet", "kitchen", "dairy", "fish product"],
    "textiles_uniforms": ["textile", "uniform", "cloth", "garment", "fabric", "shoe", "footwear",
                          "blanket", "bedding", "insignia", "yarn", "leather"],
    "printing_media": ["printing", "publication", "book", "advertis", "media", "signboard", "banner",
                       "binding", "newspaper", "broadcast"],
    "security_cleaning_services": ["security service", "guard", "cleaning", "janitorial", "waste",
                                   "pest control", "gardening", "outsourc", "manpower", "laundry",
                                   "dry-cleaning", "washing", "sewage disposal"],
    "consultancy": ["consultan", "advisory", "design services", "audit", "training services",
                    "research services", "feasibility", "architectural", "engineering services"],
    "agriculture_environment": ["agricultur", "seed", "fertili", "livestock", "fish", "forest", "tree",
                                "plant", "veterinary", "poultry", "crop", "environment", "pesticide"],
}

TITLE_KEYWORDS: dict[str, list[str]] = {
    "roads_bridges": ["road", "bridge", "culvert", "highway", "embankment", "carpeting", "hbb"],
    "buildings_civil": ["building", "boundary wall", "renovation", "repairing of", "civil work", "hostel", "plaster", "roof"],
    "water_sanitation": ["water supply", "tube well", "tubewell", "drain", "sanitation", "latrine", "pipe line", "pipeline"],
    "electrical_power": ["electric", "transformer", "solar", "generator", "cable", "substation", "meter"],
    "it_equipment": ["computer", "laptop", "printer", "software", "server", "ict", "scanner", "photocopier", "network"],
    "office_supplies": ["stationery", "stationary", "toner", "office supplies", "office equipment", "office items"],
    "furniture": ["furniture", "almirah", "chair", "table"],
    "medical": ["medicine", "medical", "surgical", "hospital", "laboratory", "reagent", "drug", "vaccine"],
    "vehicles_transport": ["vehicle", "ambulance", "motorcycle", "motor cycle", "tyre", "spare parts", "boat", "car "],
    "food_catering": ["food", "rice", "catering", "meal", "ration", "diet", "kitchen"],
    "textiles_uniforms": ["uniform", "textile", "cloth", "garment", "insignia", "shoe", "blanket"],
    "printing_media": ["printing", "publication", "book", "advertisement", "signboard", "banner"],
    "security_cleaning_services": ["security service", "cleaning", "outsourcing", "manpower", "guard", "waste"],
    "consultancy": ["consultancy", "consultant", "feasibility", "survey", "audit", "study"],
    "agriculture_environment": ["seed", "fertilizer", "fertiliser", "fish", "livestock", "tree", "plantation", "poultry", "crop"],
}


def _hits(text: str, table: dict[str, list[str]]) -> dict[str, int]:
    scores: dict[str, int] = {}
    for cat, words in table.items():
        n = sum(1 for w in words if w in text)
        if n:
            scores[cat] = n
    return scores


def label_from_tags(tags: list[str]) -> str | None:
    """Best category from the portal's tag list; None only when nothing wins outright.

    A single decisive keyword is enough. Requiring two hits discarded plainly labelled tenders,
    such as a list naming only "Furniture" and "Seats, chairs and associated parts".
    """
    text = " ".join(t.lower() for t in tags if t)
    if not text.strip():
        return None
    scores = _hits(text, TAG_KEYWORDS)
    if not scores:
        return None
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    if len(ranked) == 1 or ranked[0][1] > ranked[1][1]:
        return ranked[0][0]
    return None


def label_from_title(title: str) -> str | None:
    """Keyword fallback on the title alone; needs exactly one leading category."""
    text = " " + re.sub(r"\s+", " ", (title or "").lower()) + " "
    scores = _hits(text, TITLE_KEYWORDS)
    if not scores:
        return None
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        return None
    return ranked[0][0]
