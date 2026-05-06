from canonical_common.canonical_db import owned_columns

def test_owned_columns_chem_annotator_includes_descriptors():
    allowlist = ["inchi_key", "TotalAlcoholCount", "AldehydeCount", "HighImpactTier1Count"]
    owned = owned_columns("chem_annotator", allowlist)
    assert "TotalAlcoholCount" in owned
    assert "AldehydeCount" in owned
    assert "HighImpactTier1Count" in owned
    assert "inchi_key" not in owned  # never owned