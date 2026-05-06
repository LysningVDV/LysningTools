import pytest

# Stage 1 - Test Block C: Hemiacetal / Hemiketal Detection
@pytest.mark.parametrize("smi, expected", [
    # CH3-O-CH(OH)-CH3 : hemiacetal center; OH-bearing carbon has 1 carbon neighbor -> primary
    ("COC(O)C", {
        "HemiacetalCount": 1, "HemiketalCount": 0,
        "PrimaryAlcoholCount": 1, "SecondaryAlcoholCount": 0, "TertiaryAlcoholCount": 0,
        "TotalAlcoholCount": 1
    }),

    # (CH3)2C(OH)(OCH3) : hemiketal center (no H on carbinol carbon); carbon neighbors=2 -> secondary
    ("C(C)(O)(OC)C", {
        "HemiacetalCount": 0, "HemiketalCount": 1,
        "PrimaryAlcoholCount": 0, "SecondaryAlcoholCount": 1, "TertiaryAlcoholCount": 0,
        "TotalAlcoholCount": 1
    }),

    # Cyclic hemiacetal-like: OH-bearing carbon bonded to 1 carbon + 1 oxygen in ring -> primary
    ("C1COC(O)1", {
        "HemiacetalCount": 1, "HemiketalCount": 0,
        "PrimaryAlcoholCount": 1, "SecondaryAlcoholCount": 0, "TertiaryAlcoholCount": 0,
        "TotalAlcoholCount": 1
    }),

    # Ethanol: primary alcohol, not hemiacetal/hemiketal
    ("CCO", {
        "HemiacetalCount": 0, "HemiketalCount": 0,
        "PrimaryAlcoholCount": 1, "SecondaryAlcoholCount": 0, "TertiaryAlcoholCount": 0,
        "TotalAlcoholCount": 1
    }),

    # 2-hydroxyethyl acetate: one terminal OH -> primary; ester is not a hemiacetal/hemiketal
    ("CC(=O)OCCO", {
        "HemiacetalCount": 0, "HemiketalCount": 0,
        "PrimaryAlcoholCount": 1, "SecondaryAlcoholCount": 0, "TertiaryAlcoholCount": 0,
        "TotalAlcoholCount": 1
    }),

    # CH3-O-CH2-CH2-OH : only ONE OH -> primary count 1, total 1
    ("COCCO", {
        "HemiacetalCount": 0, "HemiketalCount": 0,
        "PrimaryAlcoholCount": 1, "SecondaryAlcoholCount": 0, "TertiaryAlcoholCount": 0,
        "TotalAlcoholCount": 1
    }),
])
def test_hemiacetal_hemiketal(run, smi, expected):
    r = run(smi)
    for k, v in expected.items():
        assert r[k] == v, f"{smi}: {k} expected {v} got {r[k]}"