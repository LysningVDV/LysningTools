import pytest
from chem_annotator.aggregator import features_for_smiles


@pytest.mark.parametrize(
    "smiles, key, expected",
    [
        # Indole (NH form)
        ("c1ccc2[nH]ccc2c1", "IndoleCount", 1),

        # Note: avoid N-methylindole SMILES variants that RDKit may fail to kekulize in some builds;
        # use skatole (3-methylindole) as a stable substituted-indole representative.
        ("Cc1c[nH]c2ccccc12", "IndoleCount", 1),

        # Furan
        ("o1cccc1", "FuranCount", 1),

        # Thiophene
        ("s1cccc1", "ThiopheneCount", 1),

        # Control: benzene should not trigger these heteroaromatics
        ("c1ccccc1", "IndoleCount", 0),
        ("c1ccccc1", "FuranCount", 0),
        ("c1ccccc1", "ThiopheneCount", 0),
    ],
)
def test_heteroaromatics_counts(smiles, key, expected):
    feats = features_for_smiles(smiles)
    assert feats["Valid"] == 1
    assert feats[key] == expected