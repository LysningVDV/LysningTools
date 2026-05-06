import pytest

# Stage 1 - Test Block E: Oxime-related tests
@pytest.mark.parametrize("smi, expected", [
    # Aldoxime: oxime OH is excluded from alcohol counts but tracked via OximeCount
    ("CC=NO", {
        "OximeCount": 1,
        "TotalAlcoholCount": 0,
        "PrimaryAlcoholCount": 0, "SecondaryAlcoholCount": 0, "TertiaryAlcoholCount": 0,
        "EnolicOHCount": 0, "PhenolCount": 0
    }),

    # Ketoxime: still excluded from alcohol counts
    ("CC(C)=NO", {
        "OximeCount": 1,
        "TotalAlcoholCount": 0,
        "PrimaryAlcoholCount": 0, "SecondaryAlcoholCount": 0, "TertiaryAlcoholCount": 0,
        "EnolicOHCount": 0, "PhenolCount": 0
    }),

    # Aromatic aldoxime: oxime, not phenol
    ("c1ccccc1C=NO", {
        "OximeCount": 1,
        "TotalAlcoholCount": 0,
        "PhenolCount": 0
    }),

    # Alkoxyamine (H2N–O–Et): not an oxime, no alcohol OH
    ("NOCC", {
        "OximeCount": 0,
        "TotalAlcoholCount": 0
    }),

    # Nitrosothioether-like: no oxime OH, no alcohol OH
    ("CSN=O", {
        "OximeCount": 0,
        "TotalAlcoholCount": 0
    }),

    # Hydroxy-oxime: one carbon alcohol OH + one oxime OH (excluded)
    # FIX: carbon alcohol is SECONDARY (OH-bearing carbon has two carbon neighbors)
    ("CC(O)C=NO", {
        "OximeCount": 1,
        "PrimaryAlcoholCount": 0,
        "SecondaryAlcoholCount": 1,
        "TertiaryAlcoholCount": 0,
        "TotalAlcoholCount": 1,
        "EnolicOHCount": 0
    }),

    # Nitrosophenol: phenolic OH counts as Phenol and as total alcohol OH
    ("Oc1ccccc1N=O", {
        "OximeCount": 0,
        "PhenolCount": 1,
        "TotalAlcoholCount": 1
    }),

    # Oxime ether (O-methyl oxime): not an oxime hydroxyl, no alcohol OH
    ("CC(=NOC)", {
        "OximeCount": 0,
        "TotalAlcoholCount": 0
    }),

    # Dioxime: two oxime OH groups, excluded from alcohol counts
    ("ON=CC=NO", {
        "OximeCount": 2,
        "TotalAlcoholCount": 0
    }),
])
def test_oxime_behavior(run, smi, expected):
    r = run(smi)
    for k, v in expected.items():
        assert r[k] == v, f"{smi}: {k} expected {v} got {r[k]}"