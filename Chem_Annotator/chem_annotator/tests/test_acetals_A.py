import pytest
from rdkit import Chem

from chem_annotator.features.acetals import count_acetals_ketals_orthoesters


def _mol(smiles: str) -> Chem.Mol:
    m = Chem.MolFromSmiles(smiles)
    assert m is not None, f"RDKit failed to parse SMILES: {smiles}"
    return m


@pytest.mark.parametrize(
    "smiles, exp_acetal, exp_ketal, exp_ortho, rationale",
    [
        # Acetal (2 OR + >=1 H on center)
        ("COC(C)OC", 1, 0, 0, "Acetal center with exactly 2 OR and >=1 H => acetal=1."),

        # Ketal (2 OR + 0 H on center)
        ("COC(C)(C)OC", 0, 1, 0, "Ketal center with exactly 2 OR and 0 H => ketal=1."),

        # Cyclic ketal-like (ring acetal)
        ("CC1(OCCO1)C", 0, 1, 0, "Cyclic ketal: center has exactly 2 OR oxygens, 0 H => ketal=1."),

        # Orthoester (exactly 3 OR on center): trimethyl orthoformate
        ("COC(OC)OC", 0, 0, 1, "Orthoester center with exactly 3 OR oxygens => ortho=1."),

        # Control: ester carbonyl excluded
        ("CC(=O)OC", 0, 0, 0, "Ester carbonyl excluded => 0,0,0."),

        # Control: diol has OH oxygens (H>0) => excluded
        ("OCCO", 0, 0, 0, "OH oxygens excluded => 0,0,0."),
    ],
)
def test_acetals_ketals_orthoesters_A(smiles, exp_acetal, exp_ketal, exp_ortho, rationale):
    m = _mol(smiles)
    a, k, o = count_acetals_ketals_orthoesters(m)
    assert (a, k, o) == (exp_acetal, exp_ketal, exp_ortho), rationale