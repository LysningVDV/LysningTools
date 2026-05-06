import pytest

# Stage 1 - Test Block D: Negative Controls (should yield ZERO alcoholic hits)
@pytest.mark.parametrize("smi, expected", [
    # Hydroxylamine (N–OH): not an alcohol
    ("NO", {"TotalAlcoholCount": 0, "PrimaryAlcoholCount": 0, "SecondaryAlcoholCount": 0,
            "TertiaryAlcoholCount": 0, "PhenolCount": 0, "EnolicOHCount": 0, "AlphaHydroxyCarbonylCount": 0}),

    # S–OH species: excluded
    ("CSO", {"TotalAlcoholCount": 0, "PrimaryAlcoholCount": 0, "SecondaryAlcoholCount": 0,
             "TertiaryAlcoholCount": 0, "PhenolCount": 0, "EnolicOHCount": 0, "AlphaHydroxyCarbonylCount": 0}),

    # Phosphoric acid (P–OH): not carbon-bound OH
    ("OP(=O)(O)O", {"TotalAlcoholCount": 0, "PrimaryAlcoholCount": 0, "SecondaryAlcoholCount": 0,
                   "TertiaryAlcoholCount": 0, "PhenolCount": 0, "EnolicOHCount": 0, "AlphaHydroxyCarbonylCount": 0}),

    # Inorganic hydroxide: not an alcohol
    ("[Na]O", {"TotalAlcoholCount": 0, "PrimaryAlcoholCount": 0, "SecondaryAlcoholCount": 0,
               "TertiaryAlcoholCount": 0, "PhenolCount": 0, "EnolicOHCount": 0, "AlphaHydroxyCarbonylCount": 0}),

    # Carboxylic acid: acidic OH excluded
    ("CC(=O)O", {"TotalAlcoholCount": 0, "PrimaryAlcoholCount": 0, "SecondaryAlcoholCount": 0,
                 "TertiaryAlcoholCount": 0, "PhenolCount": 0, "EnolicOHCount": 0, "AlphaHydroxyCarbonylCount": 0}),

    # Phenoxide anion: no OH hydrogen
    ("[O-]c1ccccc1", {"TotalAlcoholCount": 0, "PrimaryAlcoholCount": 0, "SecondaryAlcoholCount": 0,
                      "TertiaryAlcoholCount": 0, "PhenolCount": 0, "EnolicOHCount": 0, "AlphaHydroxyCarbonylCount": 0}),

    # Ether: no OH
    ("CCOC", {"TotalAlcoholCount": 0, "PrimaryAlcoholCount": 0, "SecondaryAlcoholCount": 0,
              "TertiaryAlcoholCount": 0, "PhenolCount": 0, "EnolicOHCount": 0, "AlphaHydroxyCarbonylCount": 0}),

    # Ketone: no OH
    ("CC(=O)C", {"TotalAlcoholCount": 0, "PrimaryAlcoholCount": 0, "SecondaryAlcoholCount": 0,
                 "TertiaryAlcoholCount": 0, "PhenolCount": 0, "EnolicOHCount": 0, "AlphaHydroxyCarbonylCount": 0}),
])
def test_negative_controls(run, smi, expected):
    r = run(smi)
    for k, v in expected.items():
        assert r[k] == v, f"{smi}: {k} expected {v} got {r[k]}"
