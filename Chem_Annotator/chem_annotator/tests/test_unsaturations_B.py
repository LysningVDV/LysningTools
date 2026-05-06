import pytest
from rdkit import Chem

from chem_annotator.features.unsaturations import count_cc_unsaturated_bonds


def _mol(smiles: str) -> Chem.Mol:
    m = Chem.MolFromSmiles(smiles)
    assert m is not None, f"RDKit failed to parse SMILES: {smiles}"
    return m


# Overlap / exclusion rules (explicit):
# - Only C–C bonds are considered; any bond involving heteroatoms is excluded.
# - Aromatic C–C bonds count (+1 each) but aromatic C–N, C–O, etc. do NOT.
# - Double/triple bonds count as +1 per bond (bond-counting), only when both atoms are carbon.

@pytest.mark.parametrize(
    "smiles, expected_cc_unsat, rationale",
    [
        # 1) Carbonyl only: C=O should not count (not C–C)
        (
            "CC=O",
            0,
            "Acetaldehyde: C=O present but excluded because not a C–C bond.",
        ),
        # 2) Imine: C=N should not count
        (
            "CC=N",
            0,
            "Imine: C=N excluded (not C–C).",
        ),
        # 3) Diazene: N=N should not count
        (
            "N=N",
            0,
            "Azo/diazene: no carbon atoms in the bond => excluded.",
        ),
        # 4) Nitro: hetero-atom unsaturation only; no C–C unsaturation
        (
            "C[N+](=O)[O-]",
            0,
            "Nitromethane: unsaturation is N=O (hetero-only); there are no C–C unsaturated bonds => 0.",
        ),
        # 5) Pyridine: aromatic ring has 6 bonds total; 2 are C–N (adjacent to N) => 4 C–C aromatic bonds
        (
            "n1ccccc1",
            4,
            "Pyridine: 6 aromatic ring bonds total; 2 are C–N (adjacent to N), so 4 are C–C and counted.",
        ),
        # 6) Furan: 5-member aromatic ring has 5 bonds; 2 are C–O (adjacent to O) => 3 C–C aromatic bonds
        (
            "o1cccc1",
            3,
            "Furan: 5 aromatic ring bonds total; 2 are C–O (adjacent to O), so 3 are C–C and counted.",
        ),
        # 7) Aromatic + vinyl C=C + aldehyde C=O (excluded): 6 + 1 = 7
        (
            "O=CC=Cc1ccccc1",
            7,
            "Aromatic ring contributes 6; one vinyl C=C contributes 1; aldehyde C=O excluded => 7.",
        ),
        # 8) Aromatic + alkyne sidechain: ring(6) + C≡C(1) = 7
        (
            "c1ccccc1C#C",
            7,
            "Phenylacetylene: aromatic ring 6 + one C≡C bond 1 => 7.",
        ),
    ],
)
def test_unsaturations_B_exclusions_and_heteroaromatics(smiles, expected_cc_unsat, rationale):
    m = _mol(smiles)
    got = count_cc_unsaturated_bonds(m)
    assert got == expected_cc_unsat, rationale