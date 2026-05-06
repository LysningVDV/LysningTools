import pytest

# Simple alcohol sanity checks based on substitution level

CASES = [
    # Primary alcohol
    ("CCO", {
        "PrimaryAlcoholCount": 1,
        "SecondaryAlcoholCount": 0,
        "TertiaryAlcoholCount": 0,
        "TotalAlcoholCount": 1,
    }),

    # Secondary alcohol
    ("CCC(O)C", {
        "PrimaryAlcoholCount": 0,
        "SecondaryAlcoholCount": 1,
        "TertiaryAlcoholCount": 0,
        "TotalAlcoholCount": 1,
    }),

    # Tertiary alcohol
    ("CC(C)(C)O", {
        "PrimaryAlcoholCount": 0,
        "SecondaryAlcoholCount": 0,
        "TertiaryAlcoholCount": 1,
        "TotalAlcoholCount": 1,
    }),

    # Mixed: 1° + 2°
    ("CC(O)CO", {
        "PrimaryAlcoholCount": 1,
        "SecondaryAlcoholCount": 1,
        "TertiaryAlcoholCount": 0,
        "TotalAlcoholCount": 2,
    }),
]

@pytest.mark.parametrize("smi, expected", CASES)
def test_alcohol_structures(run, smi, expected):
    """
    Tests for canonical alcohols: primary, secondary, tertiary.
    Also confirms that TotalAlcoholCount matches the sum of P, S, and T.
    """
    result = run(smi)

    for k, v in expected.items():
        assert result[k] == v, (
            f"{smi}: expected {k}={v}, got {result[k]}"
        )

    # Internal consistency check
    assert result["TotalAlcoholCount"] == (
        result["PrimaryAlcoholCount"] +
        result["SecondaryAlcoholCount"] +
        result["TertiaryAlcoholCount"]
    )

