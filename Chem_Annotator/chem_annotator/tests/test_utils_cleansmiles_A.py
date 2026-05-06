import pytest

from chem_annotator.utils import clean_smiles


# Normalization rules under test (explicit):
# - None/NaN -> ""
# - HTML entities (e.g. &nbsp;, &lt;) are unescaped
# - NBSP is normalized to space and stripped
# - ASCII control chars removed
# - If result is empty or "nbsp" -> ""
# - Multi-fragment SMILES with '.' are normalized by keeping the "largest organic fragment":
#   prefer fragments containing carbon, then highest heavy-atom count (RDKit); fallback to longest fragment.


@pytest.mark.parametrize(
    "raw, expected, rationale",
    [
        # 1) None -> empty
        pytest.param(
            None,
            "",
            "None input is treated as missing -> empty string.",
            id="none_to_empty",
        ),

        # 2) HTML NBSP-only -> empty
        pytest.param(
            "&nbsp;",
            "",
            "HTML entity NBSP decodes to whitespace, which is stripped -> empty.",
            id="html_nbsp_only_to_empty",
        ),

        # 3) Literal 'nbsp' -> empty (common artifact)
        pytest.param(
            "nbsp",
            "",
            "Literal 'nbsp' token is treated as empty placeholder -> empty.",
            id="literal_nbsp_to_empty",
        ),

        # 4) Leading/trailing whitespace trimmed, internal unchanged
        pytest.param(
            "   C=C   ",
            "C=C",
            "Whitespace is stripped; valid SMILES preserved.",
            id="strip_whitespace",
        ),

        # 5) Multi-fragment: choose largest organic fragment (prefers carbon-containing)
        pytest.param(
            "COC(=O)CC(=O)OC.[Na+]",
            "COC(=O)CC(=O)OC",
            "Salt/counterion case: keep largest carbon-containing fragment, drop inorganic counterion.",
            id="largest_organic_fragment_drops_counterion",
        ),

        # 6) Multi-fragment: choose organic fragment over inorganic even if inorganic is heavy-ish
        pytest.param(
            "[Cl-].[Na+].CCO",
            "CCO",
            "Multiple fragments: prefer carbon-containing fragment (CCO) over inorganic ions.",
            id="prefer_carbon_fragment_over_ions",
        ),

        # 7) Multi-fragment: if both organic, choose the one with more heavy atoms
        pytest.param(
            "CCO.CCOC",
            "CCOC",
            "Both fragments contain carbon; choose higher heavy-atom count fragment (CCOC > CCO).",
            id="choose_larger_organic_by_heavy_atoms",
        ),

        # 8) Control characters removed (e.g. embedded newline/tab)
        pytest.param(
            "C=C\t\n",
            "C=C",
            "ASCII control characters are removed, then stripped.",
            id="drop_control_chars",
        ),

        # 9) HTML escaped angle brackets should unescape; still returned as-is (not validated here)
        pytest.param(
            "C&lt;C",
            "C<C",
            "HTML entities are unescaped; clean_smiles does not validate SMILES syntax, only normalizes text.",
            id="unescape_html_entities",
        ),

        # 10) Multi-fragment where one fragment is unparsable: fall back to parsable organic one
        pytest.param(
            "CCO.NOT_A_SMILES",
            "CCO",
            "If a fragment is unparsable by RDKit, selection uses the best parsable fragment; here CCO.",
            id="skip_unparsable_fragment_if_possible",
        ),
    ],
)

def test_clean_smiles_A(raw, expected, rationale):
    got = clean_smiles(raw)
    assert got == expected, f"{rationale} Got={got!r} Expected={expected!r}"

def test_clean_smiles_dot_policy_fallback_longest_when_all_fragments_unparsable():
    """
    If '.' is present and RDKit fails to parse ALL fragments, clean_smiles falls back
    to the longest fragment by string length.
    """
    assert clean_smiles("not_smiles.bad") == "not_smiles"


def test_clean_smiles_dot_policy_ignores_empty_fragments():
    assert clean_smiles("..CCO..") == "CCO"
