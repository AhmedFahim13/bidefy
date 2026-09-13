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
    bangla = "সাওদা ট্রেডার্স"
    assert normalize_name(bangla) == bangla


def test_block_key_is_first_token_of_three_or_more_letters():
    assert block_key("sawda traders") == "sawda"
    assert block_key("z s technologies ltd") == "technologies"
    assert block_key("ab") == "ab"
    assert block_key("") == ""
