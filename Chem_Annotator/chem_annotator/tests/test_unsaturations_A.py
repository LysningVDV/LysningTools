import pytest
from rdkit import Chem

from chem_annotator.features.unsaturations import count_cc_unsaturated_bonds


def _mol(smiles: str) -> Chem.Mol:
    m = Chem.MolFromSmiles(smiles)
    assert m is not None, f"RDKit failed to parse SMILES: {smiles}"
    return m


# Overlap / counting rules for this module (explicit):
# - This function counts UNSATURATED C–C BONDS, not degrees of unsaturation.
# - Each C=C bond contributes +1.
# - Each C≡C bond contributes +1 (bond-based; not +2).
# - Each aromatic C–C bond contributes +1 (so benzene contributes 6).
# - Only bonds where both atoms are carbon are counted; C=O, C=N, etc. are excluded by design.

@pytest.mark.parametrize(
    "smiles, expected_cc_unsat, rationale",
    [
        # 1) Ethene: one C=C => 1
        (
            "C=C",
            1,
            "Ethene: single C=C bond => 1 C–C unsaturated bond.",
        ),
        # 2) Propene: one C=C => 1
        (
            "CC=C",
            1,
            "Propene: one C=C bond => 1.",
        ),
        # 3) 1,3-butadiene: two C=C => 2
        (
            "C=CC=C",
            2,
            "1,3-Butadiene: two distinct C=C bonds => 2.",
        ),
        # 4) 1-butyne: one C≡C => 1 (bond-counting)
        (
            "CC#C",
            1,
            "1-Butyne: one C≡C bond => counted as 1 (bond-based).",
        ),
        # 5) 2-butyne: one C≡C => 1
        (
            "CC#CC",
            1,
            "2-Butyne: one triple bond => 1.",
        ),
        # 6) Allene (propadiene): two C=C => 2
        (
            "C=C=C",
            2,
            "Allene: two C=C bonds sharing the central carbon => 2 unsaturated C–C bonds.",
        ),
        # 7) Cyclohexene: one C=C in ring => 1
        (
            "C1CCC=CC1",
            1,
            "Cyclohexene: one ring C=C => 1.",
        ),
        # 8) Benzene: aromatic ring has 6 aromatic C–C bonds => 6
        (
            "c1ccccc1",
            6,
            "Benzene: 6 aromatic C–C bonds; each aromatic C–C bond counts => 6.",
        ),
        # 9) Naphthalene: fused aromatic system has 11 aromatic C–C bonds => 11
        (
            "c1cccc2ccccc12",
            11,
            "Naphthalene: 10-carbon fused aromatic; aromatic C–C bonds total 11 => 11.",
        ),
        # 10) Styrene: benzene (6 aromatic) + one vinyl C=C => 7
        (
            "C=Cc1ccccc1",
            7,
            "Styrene: aromatic ring contributes 6 + vinyl C=C contributes 1 => total 7.",
        ),
        # (Optional core sanity: carbonyl present should not affect C–C unsaturation.
        # Uncomment if you want 11 cases; currently staying at 10.)
        # (
        #     "CC(=O)C=C",
        #     1,
        #     "Methyl vinyl ketone: one C=C contributes 1; C=O is excluded because not C–C.",
        # ),
    ],
)
def test_unsaturations_A_cc_unsat(smiles, expected_cc_unsat, rationale):
    m = _mol(smiles)
    got = count_cc_unsaturated_bonds(m)
    assert got == expected_cc_unsat, rationale