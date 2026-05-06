import pytest
from rdkit import Chem

from chem_annotator.features.unsaturations import (
    count_cc_unsaturated_bonds,
    count_cc_alkene_bonds,
    count_cc_alkyne_bonds,
)


def _mol(smiles: str) -> Chem.Mol:
    m = Chem.MolFromSmiles(smiles)
    assert m is not None, f"RDKit failed to parse SMILES: {smiles}"
    return m


@pytest.mark.parametrize(
    "smiles, exp_alkene, exp_alkyne, exp_unsat_cc",
    [
        ("C=C", 1, 0, 1),             # ethene
        ("C#C", 0, 1, 1),             # ethyne
        ("CC=C", 1, 0, 1),            # propene
        ("c1ccccc1", 0, 0, 6),        # benzene: aromatic bonds count in unsat_cc, but not in alkene/alkyne
        ("C=C.C#C", 1, 1, 2),         # multi-fragment parsing (MolFromSmiles keeps both fragments here)
    ],
)
def test_alkene_alkyne_counts(smiles, exp_alkene, exp_alkyne, exp_unsat_cc):
    m = _mol(smiles)
    assert count_cc_alkene_bonds(m) == exp_alkene
    assert count_cc_alkyne_bonds(m) == exp_alkyne
    assert count_cc_unsaturated_bonds(m) == exp_unsat_cc