import pytest
from rdkit import Chem

from chem_annotator.features.ethers import ether_category_counts


def _mol(smiles: str) -> Chem.Mol:
    m = Chem.MolFromSmiles(smiles)
    assert m is not None, f"RDKit failed to parse SMILES: {smiles}"
    return m


@pytest.mark.parametrize(
    "smiles,expected",
    [
        # -------------------------
        # Acyclic ethers
        # -------------------------
        pytest.param(
            "COC",
            {"EtherCount_Total": 1, "EtherCount_Acyclic": 1, "EtherCount_Cyclic": 0, "EpoxideCount": 0},
            id="dimethyl_ether_acyclic",
        ),
        pytest.param(
            "COCCOC",
            {"EtherCount_Total": 2, "EtherCount_Acyclic": 2, "EtherCount_Cyclic": 0, "EpoxideCount": 0},
            id="dimethoxyethane_two_acyclic",
        ),

        # -------------------------
        # Cyclic ethers (non-epoxides)
        # -------------------------
        pytest.param(
            "C1CCOC1",
            {"EtherCount_Total": 1, "EtherCount_Acyclic": 0, "EtherCount_Cyclic": 1, "EpoxideCount": 0},
            id="thf_cyclic",
        ),
        pytest.param(
            "O1CCOCC1",
            {"EtherCount_Total": 2, "EtherCount_Acyclic": 0, "EtherCount_Cyclic": 2, "EpoxideCount": 0},
            id="dioxane_two_cyclic",
        ),

        # -------------------------
        # Epoxides
        # -------------------------
        pytest.param(
            "C1CO1",
            {"EtherCount_Total": 1, "EtherCount_Acyclic": 0, "EtherCount_Cyclic": 1, "EpoxideCount": 1},
            id="oxirane_epoxide",
        ),
        pytest.param(
            "CC1CO1",
            {"EtherCount_Total": 1, "EtherCount_Acyclic": 0, "EtherCount_Cyclic": 1, "EpoxideCount": 1},
            id="propylene_oxide_epoxide",
        ),

        # -------------------------
        # Aromatic / mixed ethers (acyclic)
        # -------------------------
        pytest.param(
            "COc1ccccc1",
            {"EtherCount_Total": 1, "EtherCount_Acyclic": 1, "EtherCount_Cyclic": 0, "EpoxideCount": 0},
            id="anisole_acyclic",
        ),
        pytest.param(
            "c1ccc(cc1)Oc2ccccc2",
            {"EtherCount_Total": 1, "EtherCount_Acyclic": 1, "EtherCount_Cyclic": 0, "EpoxideCount": 0},
            id="diphenyl_ether_acyclic",
        ),

        # -------------------------
        # Esters / carbonates — excluded
        # -------------------------
        pytest.param(
            "CC(=O)OC",
            {"EtherCount_Total": 0, "EtherCount_Acyclic": 0, "EtherCount_Cyclic": 0, "EpoxideCount": 0},
            id="methyl_acetate_excluded",
        ),
        pytest.param(
            "CCOC(=O)OCC",
            {"EtherCount_Total": 0, "EtherCount_Acyclic": 0, "EtherCount_Cyclic": 0, "EpoxideCount": 0},
            id="diethyl_carbonate_excluded",
        ),
    ],
)
def test_ethers_A_category_counts(smiles, expected):
    counts = ether_category_counts(_mol(smiles))

    assert counts == expected

    # Invariants
    assert counts["EtherCount_Total"] == counts["EtherCount_Acyclic"] + counts["EtherCount_Cyclic"]
    assert 0 <= counts["EpoxideCount"] <= counts["EtherCount_Cyclic"] <= counts["EtherCount_Total"]