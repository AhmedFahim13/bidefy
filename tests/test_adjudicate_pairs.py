"""The rule that merged 1,645 name pairs in the published archive, and had no tests.

Coverage put this file at nought percent. It is not a reporting script: it decides which firms are
the same firm, and every decision it got wrong is baked into the bidder profiles, the award totals
and the concentration flags on the live site. A wrong merge invents a contractor that won work it
never won; a wrong keep splits one firm's record in half. Both are published as fact.

The cases below are the ones the docstring promises, stated as tests so the promise is enforced.
"""
from tools.adjudicate_pairs import core, decide


class TestCore:
    def test_punctuation_and_case_carry_no_identity(self):
        assert core("MA-BABA CONSTRUCTION LTD.") == core("Ma Baba Construction")

    def test_honorifics_are_dropped(self):
        assert core("Md. Kamal Enterprise") == core("Kamal Enterprise")
        assert core("Alhaj Rafiq Traders") == core("Rafiq Trader")

    def test_legal_suffixes_are_dropped(self):
        assert core("Rahman and Sons Pvt Ltd") == core("Rahman")

    def test_a_run_of_initials_becomes_one_token(self):
        """"S. M." and "S.M" must read the same, or every initialled firm splits in two."""
        assert core("S. M. Enterprise") == core("S.M Enterprise") == ("sm", "enterprise")

    def test_plurals_are_folded_to_the_singular(self):
        assert core("Karim Enterprises") == core("Karim Enterprise")

    def test_the_trade_word_is_kept(self):
        """Dropping it would merge every firm an owner's name appears in."""
        assert "construction" in core("Kamal Construction")
        assert core("Kamal Enterprise") != core("Kamal Construction")


class TestDecide:
    def test_the_same_firm_written_differently_merges(self):
        assert decide("M/S Ma Baba Construction", "MA-BABA CONSTRUCTION LTD.") == "merge"
        assert decide("Md. Kamal Enterprise", "Kamal Enterprises") == "merge"

    def test_a_reordered_name_merges(self):
        assert decide("Baba Ma Construction", "Ma Baba Construction") == "merge"

    def test_different_initials_are_different_firms(self):
        """The case the docstring names: one character apart, and not the same company."""
        assert decide("S. M. Enterprise", "S.S Enterprise") == "keep"

    def test_a_different_trade_word_is_a_different_firm(self):
        assert decide("Kamal Enterprise", "Kamal Construction") == "keep"

    def test_a_different_number_is_a_different_firm(self):
        assert decide("Unit 2 Brickfield", "Unit 3 Brickfield") == "keep"

    def test_an_extra_word_is_left_for_a_human(self):
        """Abstaining is a decision too: "Islam Enterprise" may or may not be "S.R Islam Enterprise"."""
        assert decide("Islam Enterprise", "S.R Islam Enterprise") == ""

    def test_a_truncated_spelling_is_left_for_a_human(self):
        assert decide("Rahman Construction", "Rahmania Construction") == ""

    def test_a_name_with_no_identifying_part_is_left_for_a_human(self):
        """Stripping everything means the rule has nothing to compare, not that they match."""
        assert decide("Md.", "Ltd") == ""
        assert decide("", "Kamal Enterprise") == ""

    def test_the_rule_is_symmetric(self):
        """An asymmetric merge rule would give a different archive depending on row order."""
        pairs = [("M/S Ma Baba Construction", "MA-BABA CONSTRUCTION LTD."),
                 ("S. M. Enterprise", "S.S Enterprise"),
                 ("Islam Enterprise", "S.R Islam Enterprise"),
                 ("Unit 2 Brickfield", "Unit 3 Brickfield"),
                 ("Rahman Construction", "Rahmania Construction")]
        for a, b in pairs:
            assert decide(a, b) == decide(b, a), f"{a!r} vs {b!r} depends on the order"

    def test_a_name_never_fails_to_match_itself(self):
        for name in ("Md. Kamal Enterprise", "S. M. Traders Ltd", "MA-BABA CONSTRUCTION",
                     "Unit 2 Brickfield", "Rahman and Sons"):
            assert decide(name, name) == "merge"
