import pytest

# Stage 1 - Test Block B: Phenols, Enols, Alpha-hydroxy Carbonyls
# Strict IUPAC class logic:
# - "Alcohols" (primary/secondary/tertiary) require OH on a saturated carbon.
# - Enols and phenols are separate classes (not counted as alcohols).
# - TotalAlcoholCount counts all OH groups regardless of class.

@pytest.mark.parametrize("smi, expected", [
    ("Oc1ccccc1", {
        "PhenolCount": 1,
        "EnolicOHCount": 0,
        "AlphaHydroxyCarbonylCount": 0,
        "PrimaryAlcoholCount": 0, "SecondaryAlcoholCount": 0, "TertiaryAlcoholCount": 0,
        "TotalAlcoholCount": 1
    }),

    ("C=CO", {  # vinyl alcohol (enol)
        "PhenolCount": 0,
        "EnolicOHCount": 1,
        "AlphaHydroxyCarbonylCount": 0,
        "PrimaryAlcoholCount": 0, "SecondaryAlcoholCount": 0, "TertiaryAlcoholCount": 0,
        "TotalAlcoholCount": 1
    }),

    ("CC=CO", {  # enol
        "PhenolCount": 0,
        "EnolicOHCount": 1,
        "AlphaHydroxyCarbonylCount": 0,
        "PrimaryAlcoholCount": 0, "SecondaryAlcoholCount": 0, "TertiaryAlcoholCount": 0,
        "TotalAlcoholCount": 1
    }),

    ("CC(O)C=O", {  # alpha-hydroxy carbonyl
        "PhenolCount": 0,
        "EnolicOHCount": 0,
        "AlphaHydroxyCarbonylCount": 1,
        "PrimaryAlcoholCount": 0, "SecondaryAlcoholCount": 0, "TertiaryAlcoholCount": 0,
        "TotalAlcoholCount": 1
    }),

    ("OCC=O", {  # alpha-hydroxy carbonyl
        "PhenolCount": 0,
        "EnolicOHCount": 0,
        "AlphaHydroxyCarbonylCount": 1,
        "PrimaryAlcoholCount": 0, "SecondaryAlcoholCount": 0, "TertiaryAlcoholCount": 0,
        "TotalAlcoholCount": 1
    }),

    ("Oc1ccccc1C=C", {  # substituted phenol
        "PhenolCount": 1,
        "EnolicOHCount": 0,
        "AlphaHydroxyCarbonylCount": 0,
        "PrimaryAlcoholCount": 0, "SecondaryAlcoholCount": 0, "TertiaryAlcoholCount": 0,
        "TotalAlcoholCount": 1
    }),

    ("C=CCO", {  # allyl alcohol (OH on saturated carbon -> alcohol, primary)
        "PhenolCount": 0,
        "EnolicOHCount": 0,
        "AlphaHydroxyCarbonylCount": 0,
        "PrimaryAlcoholCount": 1, "SecondaryAlcoholCount": 0, "TertiaryAlcoholCount": 0,
        "TotalAlcoholCount": 1
    }),

    ("OC(C)=C=O", {  # enol adjacent to carbonyl
        "PhenolCount": 0,
        "EnolicOHCount": 1,
        "AlphaHydroxyCarbonylCount": 0,
        "PrimaryAlcoholCount": 0, "SecondaryAlcoholCount": 0, "TertiaryAlcoholCount": 0,
        "TotalAlcoholCount": 1
    }),
])
def test_phenols_enols_alpha_hydroxy(run, smi, expected):
    r = run(smi)
    for k, v in expected.items():
        assert r[k] == v, f"{smi}: {k} expected {v} got {r[k]}"