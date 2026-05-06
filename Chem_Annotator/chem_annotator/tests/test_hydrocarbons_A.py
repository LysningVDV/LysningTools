import pytest
from chem_annotator.aggregator import features_for_smiles


@pytest.mark.parametrize(
    "smiles, exp_pure, exp_arom, exp_aliph, exp_rings, exp_terp",
    [
        ("c1ccccc1", 1, 1, 0, 1, 0),     # benzene
        ("C1CCCCC1", 1, 0, 1, 1, 0),     # cyclohexane
        ("Cc1ccccc1", 1, 1, 0, 1, 0),    # toluene
        ("CCO", 0, 0, 0, 0, 0),          # ethanol (not pure hydrocarbon)
    ],
)
def test_hydrocarbon_flags(smiles, exp_pure, exp_arom, exp_aliph, exp_rings, exp_terp):
    feats = features_for_smiles(smiles)
    assert feats["Valid"] == 1
    assert feats["IsPureHydrocarbon"] == exp_pure
    assert feats["IsHydrocarbonAromatic"] == exp_arom
    assert feats["IsHydrocarbonAliphatic"] == exp_aliph
    assert feats["HydrocarbonRingCount"] == exp_rings
    assert feats["IsTerpeneHydrocarbon"] == exp_terp


def test_terpene_hydrocarbon_flag_on_limonene_like():
    # Limonene (common terpene hydrocarbon); should be pure hydrocarbon and terpene-like
    feats = features_for_smiles("CC1=CCC(CC1)C(=C)C")  # one common limonene SMILES form
    assert feats["Valid"] == 1
    assert feats["IsPureHydrocarbon"] == 1
    assert feats["TerpeneLikeUnitCount"] >= 1
    assert feats["IsTerpeneHydrocarbon"] == 1