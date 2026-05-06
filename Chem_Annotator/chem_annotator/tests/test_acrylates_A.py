import pytest
from chem_annotator.aggregator import features_for_smiles


@pytest.mark.parametrize(
    "smiles, key, expected",
    [
        # Methyl acrylate
        ("C=CC(=O)OC", "AcrylateEsterCount", 1),
        ("C=CC(=O)OC", "MethacrylateEsterCount", 0),

        # Methyl methacrylate
        ("C=C(C)C(=O)OC", "MethacrylateEsterCount", 1),
        ("C=C(C)C(=O)OC", "AcrylateEsterCount", 0),

        # Acrylic acid should NOT count (not an ester)
        ("C=CC(=O)O", "AcrylateEsterCount", 0),

        # Allyl acetate is an ester but NOT an acrylate (double bond is on alcohol side)
        ("C=CCOC(=O)C", "AcrylateEsterCount", 0),
    ],
)
def test_acrylate_methacrylate_counts(smiles, key, expected):
    feats = features_for_smiles(smiles)
    assert feats["Valid"] == 1
    assert feats[key] == expected