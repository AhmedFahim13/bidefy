from bidefy.models import cpv


def _labels(*codes: str) -> list[str]:
    """Official descriptions for the given codes, the way the portal lists them."""
    by_label, _ = cpv._table()
    by_code = {}
    for label, code in by_label.items():
        by_code.setdefault(code, label)
    return [by_code[c] for c in codes]


def _division_groups(division: str) -> list[str]:
    """One official code per group in a division, as a buyer ticking the whole division would get."""
    by_label, _ = cpv._table()
    first = {}
    for code in sorted(by_label.values()):
        if code.startswith(division):
            first.setdefault(code[:4], code)
    return list(first.values())


def test_the_portal_descriptions_resolve_to_official_codes():
    assert cpv.code_for("Site preparation work") == "45100000"
    assert cpv.code_for("  Electric motors, generators and transformers ") == "31100000"
    assert cpv.code_for("Medical devices") == "33100000"          # an older CPV 2003 wording
    assert cpv.code_for("not a procurement category") is None


def test_site_preparation_is_construction_not_food():
    """The keyword labeller read 'preparation' as containing 'ration' and called this food."""
    got = cpv.label(["Site preparation work"])
    assert got.sector == "construction" and got.category is None


def test_a_specific_road_pick_gives_the_sub_type():
    got = cpv.label(_labels("45000000", "45233000", "45233100"))
    assert got.sector == "construction" and got.category == "roads_bridges"


def test_a_whole_construction_division_hides_the_sub_type():
    """77 percent of construction tenders tick every group, which says nothing about roads versus buildings."""
    got = cpv.label(_labels(*_division_groups("45")))
    assert got.sector == "construction" and got.category is None


def test_computer_repair_is_it():
    got = cpv.label(["Repair and maintenance services of personal computers", "Maintenance and repair of office machinery"])
    assert got.sector == "it_equipment" and got.category == "it_equipment"


def test_a_whole_repair_and_installation_pick_is_not_it():
    """Before the fix, leftover installation codes outvoted the rest and 582 civil repairs became IT."""
    tags = ["Repair, maintenance and installation services", "Installation services"]
    tags += _labels(*_division_groups("50"), *_division_groups("51")[:8])
    assert cpv.label(tags).sector is None


def test_the_legacy_manufactured_goods_pick_is_not_read_as_furniture():
    """Of 983 tenders carrying it, 431 were not furniture."""
    tags = ["Manufactured goods, furniture, handicrafts, special-purpose products and associated consumables"]
    tags += _labels("39100000", "39140000", "39150000", "39160000", "37500000", "18510000")
    assert cpv.label(tags).sector is None


def test_a_deliberately_silent_code_does_not_borrow_its_division():
    """Jewellery sits inside the clothing division but must not vote for textiles."""
    assert cpv.label(_labels("18510000")).sector is None
    assert cpv.label(_labels("18100000")).sector == "textiles_uniforms"


def test_unrecognised_tags_are_ignored_not_guessed():
    assert cpv.label(["Nothing the vocabulary knows"]) == cpv.CpvLabel(None, None, 0, 0)
