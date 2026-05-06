import pytest

# Stage 1 - Test Block F: Complex molecules combining multiple alcohol motifs
@pytest.mark.parametrize("smi, expected", [
    # Phenol + benzyl alcohol
    ("Oc1ccccc1CO", {
        "PhenolCount": 1,
        "PrimaryAlcoholCount": 1, "SecondaryAlcoholCount": 0, "TertiaryAlcoholCount": 0,
        "EnolicOHCount": 0, "AlphaHydroxyCarbonylCount": 0,
        "TotalAlcoholCount": 2
    }),

    # Vinyl ether alcohol: CH2=CH-O-CH(CH3)-OH (NOT an enol; only one OH)
    ("C=COC(C)O", {
        "PhenolCount": 0,
        "EnolicOHCount": 0,
        "AlphaHydroxyCarbonylCount": 0,
        "PrimaryAlcoholCount": 1, "SecondaryAlcoholCount": 0, "TertiaryAlcoholCount": 0,
        "TotalAlcoholCount": 1
    }),

    # Ph-CH(OH)-CHO : benzylic + alpha-hydroxy carbonyl; only ONE OH total
    ("O=CC(O)c1ccccc1", {
        "BenzylicAlcoholCount": 1,
        "AlphaHydroxyCarbonylCount": 1,
        "PrimaryAlcoholCount": 0, "SecondaryAlcoholCount": 0, "TertiaryAlcoholCount": 0,
        "EnolicOHCount": 0, "PhenolCount": 0,
        "TotalAlcoholCount": 1
    }),

    # CH3O-CH(OH)-CH2OH : hemiacetal + two primary alcohol OH sites
    ("COC(O)CO", {
        "HemiacetalCount": 1, "HemiketalCount": 0,
        "PrimaryAlcoholCount": 2, "SecondaryAlcoholCount": 0, "TertiaryAlcoholCount": 0,
        "PhenolCount": 0, "EnolicOHCount": 0, "AlphaHydroxyCarbonylCount": 0,
        "TotalAlcoholCount": 2
    }),

    # Phenol + propyl alcohol side chain
    ("Oc1ccc(CCO)cc1", {
        "PhenolCount": 1,
        "PrimaryAlcoholCount": 1, "SecondaryAlcoholCount": 0, "TertiaryAlcoholCount": 0,
        "EnolicOHCount": 0, "AlphaHydroxyCarbonylCount": 0,
        "TotalAlcoholCount": 2
    }),

    # Two alcohols: allylic+benzylic secondary OH, plus benzylic tertiary OH
    ("C=CC(O)c1ccccc1C(O)(C)C", {
        "AllylicAlcoholCount": 1,
        "BenzylicAlcoholCount": 2,
        "PrimaryAlcoholCount": 0, "SecondaryAlcoholCount": 1, "TertiaryAlcoholCount": 1,
        "PhenolCount": 0, "EnolicOHCount": 0, "AlphaHydroxyCarbonylCount": 0,
        "TotalAlcoholCount": 2
    }),

    # CH2=CH-O-C(CH3)(OH)-CH2OH : hemiketal + one primary OH + one secondary OH; NOT enolic; total OH=2
    ("C=COC(C)(O)CO", {
        "HemiacetalCount": 0, "HemiketalCount": 1,
        "PhenolCount": 0,
        "EnolicOHCount": 0,
        "AlphaHydroxyCarbonylCount": 0,
        "PrimaryAlcoholCount": 1, "SecondaryAlcoholCount": 1, "TertiaryAlcoholCount": 0,
        "TotalAlcoholCount": 2
    }),
])
def test_complex_combinations(run, smi, expected):
    r = run(smi)
    for k, v in expected.items():
        assert r[k] == v, f"{smi}: {k} expected {v} got {r[k]}"