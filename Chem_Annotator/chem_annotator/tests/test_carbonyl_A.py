
import pytest
from rdkit import Chem

from chem_annotator.features.carbonyl import count_lactones_split


def _mol(smiles: str) -> Chem.Mol:
    m = Chem.MolFromSmiles(smiles)
    assert m is not None, f"RDKit failed to parse SMILES: {smiles}"
    return m


@pytest.mark.parametrize(
    "smiles,expected",
    [
        # -------------------------
        # Core single-functionality
        # -------------------------

        # Methyl acetate: one ester, not cyclic => 0 lactones, 1 open ester, total 1
        # Logic: ester present but acyl carbon and alkoxy oxygen are not in the same ring.
        pytest.param("CC(=O)OC", (0, 1, 1), id="methyl_acetate_open_ester"),

        # Ethyl benzoate: aromatic acyl ester, still open => 0 lactones, 1 open, total 1
        pytest.param("CCOC(=O)c1ccccc1", (0, 1, 1), id="ethyl_benzoate_open_ester"),

        # Gamma-butyrolactone: classic 5-membered lactone => 1 lactone, 0 open, total 1
        # Logic: cyclic ester; the ester oxygen is part of the ring containing the acyl carbon.
        pytest.param("O=C1OCCC1", (1, 0, 1), id="gamma_butyrolactone_lactone"),

        # Delta-valerolactone: 6-membered lactone => 1 lactone, 0 open, total 1
        pytest.param("O=C1OCCCC1", (1, 0, 1), id="delta_valerolactone_lactone"),

        # Coumarin: aromatic fused lactone (benzopyran-2-one) should still count as a lactone
        pytest.param("O=C1OC=2C=CC=CC2C=C1", (1, 0, 1), id="coumarin_aromatic_lactone"),

        # -------------------------
        # Multiple esters
        # -------------------------

        # Dimethyl succinate: two open ester groups => lact 0, open 2, total 2
        pytest.param("COC(=O)CCC(=O)OC", (0, 2, 2), id="dimethyl_succinate_two_open_esters"),

        # Diethyl malonate: two open ester groups => lact 0, open 2, total 2
        pytest.param("CCOC(=O)CC(=O)OCC", (0, 2, 2), id="diethyl_malonate_two_open_esters"),

        # Glycolide (1,4-dioxane-2,5-dione): cyclic diester with two ester motifs in the ring.
        # Expected: both ester matches correspond to lactone-type closure => lact 2, open 0, total 2
        pytest.param("O=C1COC(=O)CO1", (2, 0, 2), id="glycolide_two_lactone_motifs"),

        # Non-ester carbonyl control: acetone (ketone) => no ester matches => all zeros
        pytest.param("CC(=O)C", (0, 0, 0), id="acetone_no_ester"),
    ],
)
def test_count_lactones_split_core(smiles, expected):
    """
    Tests for count_lactones_split().

    Chemical logic / conventions:
      - Lactone = cyclic ester (intramolecular ester): the acyl carbon and alkoxy oxygen belong to the same ring.
      - Open ester = ester group not forming a ring closure between acyl carbon and alkoxy oxygen.
      - Multi-ester molecules should return totals equal to number of ester substructure matches.

    Overlap rules:
      - A given ester match is classified as either lactone OR open ester (mutually exclusive in this function).
      - Total = lactone + open ester by construction.
    """
    m = _mol(smiles)
    lact, open_est, total = count_lactones_split(m)
    assert (lact, open_est, total) == expected
    assert lact + open_est == total
