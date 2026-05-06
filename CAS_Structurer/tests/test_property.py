import pytest
from hypothesis import given, strategies as st
from cas_structurer.cas_logic import normalize_and_repair_token, split_cas_cell

@given(st.text(min_size=5, max_size=12))
def test_random_typo_robustness(random_cas):
    # Try random typos in CAS-like strings
    # Should never crash, and should always return a tuple (token, status)
    try:
        token, status = normalize_and_repair_token(random_cas, "", "", {}, {})
        assert isinstance(token, str)
        assert isinstance(status, str)
    except Exception as e:
        pytest.fail(f"normalize_and_repair_token crashed on input: {random_cas!r} ({e})")


@given(
    st.lists(
        st.text(min_size=1, max_size=12, alphabet=st.characters(blacklist_categories=['Cc'])),
        min_size=2,
        max_size=5
    ),
    st.sampled_from(["/", ";", ",", "\\", "\n", " ", "\t"])
)
def test_split_cas_cell_random_delimiters(tokens, delim):
    val = delim.join(tokens)
    result = split_cas_cell(val)
    import re
    SPLIT_REGEX = re.compile(r"[\\/;,\r\n ]+")
    for t in tokens:
        fragments = [frag for frag in SPLIT_REGEX.split(t) if frag.strip()]
        for frag in fragments:
            assert frag.strip() in [r.strip() for r in result]

