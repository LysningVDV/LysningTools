import physprops.main as m

def test_smiles_heuristic_rejects_digits():
    assert m._looks_like_smiles_value("0") is False
    assert m._looks_like_smiles_value("49") is False
    assert m._looks_like_smiles_value(" 12 ") is False