from bidefy.models.categories import CATEGORIES, LABELS, label_from_tags, label_from_title


def test_categories_are_stable_slugs():
    assert len(CATEGORIES) == 15 and all(c == c.lower() and " " not in c for c in CATEGORIES)
    assert set(LABELS) == set(CATEGORIES)


def test_tags_map_to_categories():
    assert label_from_tags(["Computer equipment and supplies", "Software", "Servers"]) == "it_equipment"
    assert label_from_tags(["Construction work for highways, roads", "Road-repair works"]) == "roads_bridges"
    assert label_from_tags(["Pharmaceutical products", "Medical equipments"]) == "medical"
    assert label_from_tags(["Office and computing machinery", "Stationery"]) in ("office_supplies", "it_equipment")


def test_ambiguous_or_unknown_returns_none():
    assert label_from_tags([]) is None
    assert label_from_tags(["Zebra breeding services"]) is None


def test_title_fallback_is_keyword_based():
    assert label_from_title("Construction of RCC bridge over Kaliganga river") == "roads_bridges"
    assert label_from_title("Procurement of furniture for Taxes Zone") == "furniture"
    assert label_from_title("Something entirely unrelated") is None
