import pytest

# Stage 1 - Test Block A: Basic alcohol classifications (primary, secondary, tertiary)
# IUPAC classification: based on the degree (number of carbon substituents) on the OH-bearing carbon.
@pytest.mark.parametrize("smi, expected", [
    # Ethanol: primary alcohol
    ("CCO", {
        "PrimaryAlcoholCount": 1, "SecondaryAlcoholCount": 0, "TertiaryAlcoholCount": 0,
        "PhenolCount": 0, "AlphaHydroxyCarbonylCount": 0, "EnolicOHCount": 0,
        "TotalAlcoholCount": 1
    }),

    # 2-butanol: secondary alcohol
    ("CCC(O)C", {
        "PrimaryAlcoholCount": 0, "SecondaryAlcoholCount": 1, "TertiaryAlcoholCount": 0,
        "PhenolCount": 0, "AlphaHydroxyCarbonylCount": 0, "EnolicOHCount": 0,
        "TotalAlcoholCount": 1
    }),

    # tert-butanol: tertiary alcohol
    ("CC(C)(C)O", {
        "PrimaryAlcoholCount": 0, "SecondaryAlcoholCount": 0, "TertiaryAlcoholCount": 1,
        "PhenolCount": 0, "AlphaHydroxyCarbonylCount": 0, "EnolicOHCount": 0,
        "TotalAlcoholCount": 1
    }),

    # 1,2-propanediol: one primary OH + one secondary OH
    ("CC(O)CO", {
        "PrimaryAlcoholCount": 1, "SecondaryAlcoholCount": 1, "TertiaryAlcoholCount": 0,
        "PhenolCount": 0, "AlphaHydroxyCarbonylCount": 0, "EnolicOHCount": 0,
        "TotalAlcoholCount": 2
    }),

    # FIXED: isopropanol (2-propanol) is secondary, not primary
    ("CC(C)O", {
        "PrimaryAlcoholCount": 0, "SecondaryAlcoholCount": 1, "TertiaryAlcoholCount": 0,
        "PhenolCount": 0, "AlphaHydroxyCarbonylCount": 0, "EnolicOHCount": 0,
        "TotalAlcoholCount": 1
    }),

    # Same molecule as above (isopropanol) but alternate SMILES ordering; still secondary alcohol
    ("C(C)(O)C", {
        "PrimaryAlcoholCount": 0, "SecondaryAlcoholCount": 1, "TertiaryAlcoholCount": 0,
        "PhenolCount": 0, "AlphaHydroxyCarbonylCount": 0, "EnolicOHCount": 0,
        "TotalAlcoholCount": 1
    }),

    # FIXED: same molecule as tert-butanol but alternate SMILES ordering; still tertiary alcohol
    ("OC(C)(C)C", {
        "PrimaryAlcoholCount": 0, "SecondaryAlcoholCount": 0, "TertiaryAlcoholCount": 1,
        "PhenolCount": 0, "AlphaHydroxyCarbonylCount": 0, "EnolicOHCount": 0,
        "TotalAlcoholCount": 1
    }),
])
def test_basic_classifications(run, smi, expected):
    r = run(smi)
    for k, v in expected.items():
        assert r[k] == v, f"{smi}: {k} expected {v} got {r[k]}"