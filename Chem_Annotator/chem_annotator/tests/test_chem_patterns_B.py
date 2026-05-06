
import pytest
from rdkit import Chem

import chem_annotator.chem_patterns as cp


def _mol(smiles: str) -> Chem.Mol:
    m = Chem.MolFromSmiles(smiles)
    assert m is not None, f"RDKit failed to parse SMILES: {smiles}"
    return m


@pytest.mark.parametrize(
    "patt_name,smiles,expected",
    [
        # -------------------------
        # Ether subtypes + overlaps
        # -------------------------

        # THF: cyclic ether. O is in a ring => Ether_Ring True.
        pytest.param("Ether_Ring", "C1CCOC1", True, id="ether_ring_thf_pos"),
        # Ether_Aliphatic explicitly requires !R on the oxygen and carbons, so THF should be excluded.
        pytest.param("Ether_Aliphatic", "C1CCOC1", False, id="ether_aliphatic_thf_neg_due_to_ring"),

        # 1,4-dioxane: cyclic ether with two ring oxygens; should match Ether_Ring.
        pytest.param("Ether_Ring", "O1CCOCC1", True, id="ether_ring_dioxane_pos"),

        # Diphenyl ether: aromatic–aromatic ether.
        pytest.param("Ether_Aromatic", "c1ccc(cc1)Oc2ccccc2", True, id="ether_aromatic_diphenyl_ether_pos"),
        # Should not be classified as mixed (both sides aromatic).
        pytest.param("Ether_Mixed", "c1ccc(cc1)Oc2ccccc2", False, id="ether_mixed_diphenyl_ether_neg"),

        # Anisole: aromatic–aliphatic ether (mixed).
        pytest.param("Ether_Mixed", "COc1ccccc1", True, id="ether_mixed_anisole_pos"),
        # Should not be aromatic–aromatic (only one aromatic substituent).
        pytest.param("Ether_Aromatic", "COc1ccccc1", False, id="ether_aromatic_anisole_neg"),

        # -------------------------
        # Nitrile + exclusion
        # -------------------------

        # Acetonitrile: C#N should match nitrile.
        pytest.param("Nitrile", "CC#N", True, id="nitrile_acetonitrile_pos"),
        # Methyl isocyanide: N#C is NOT a nitrile; should not match [CX2]#N.
        pytest.param("Nitrile", "C[N+]#[C-]", False, id="nitrile_should_not_match_isonitrile_neg"),

        # -------------------------
        # Isoprenyl heuristic + negative control
        # -------------------------

        # Isoprene contains C=C(C)C motif (heuristic).
        pytest.param("Isoprenyl", "C=CC(=C)C", True, id="isoprenyl_isoprene_pos"),
        # Allyl alcohol lacks the branch methyl on the vinylic carbon => should not match.
        pytest.param("Isoprenyl", "C=CCO", False, id="isoprenyl_should_not_match_allyl_alcohol_neg"),
    ],
)
def test_chem_patterns_B_edge_cases(patt_name, smiles, expected):
    """
    Edge/negative-control suite for SMARTS patterns used downstream.

    Ether overlap rules:
      - Ether_Ring: oxygen atom is in a ring (cyclic ether).
      - Ether_Aliphatic/Mixed/Aromatic are substituent-based subtypes.
      - Ring status should exclude Ether_Aliphatic by definition of that SMARTS.

    Nitrile:
      - True nitrile is -C#N (carbon triple-bond nitrogen).
      - Isonitrile/isocyanide is -N#C and should not match nitrile SMARTS.

    Isoprenyl motif:
      - Heuristic screen: should be selective for the branched C=C(C)C motif.
      - Negative controls ensure the pattern isn't too broad.
    """
    patt = cp.PATTS.get(patt_name)
    assert patt is not None, f"Pattern {patt_name} missing from PATTS. Available: {sorted(cp.PATTS)}"
    m = _mol(smiles)
    assert m.HasSubstructMatch(patt) is expected
