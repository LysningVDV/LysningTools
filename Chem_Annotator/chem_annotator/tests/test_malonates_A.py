import pytest
from rdkit import Chem

from chem_annotator.features.malonates import count_malonate_structures


def _mol(smiles: str) -> Chem.Mol:
    m = Chem.MolFromSmiles(smiles)
    assert m is not None, f"RDKit failed to parse SMILES: {smiles}"
    return m


# Overlap rules (explicit):
# - Each detected malonate center contributes to exactly one subtype bucket: diester OR half-ester OR diacid (mutually exclusive).
# - total counts the number of malonate centers (visited central carbons), so total should equal diester+half+diacid.
# - A malonate center is a carbon atom single-bonded to two carbonyl carbons, each being a C(=O)-O(ester/acid) group. [1](https://lysninginnovationconsultant-my.sharepoint.com/personal/villeneuve_lysning_nl/Documents/Microsoft%20Copilot%20Chat%20Files/malonates.py)

@pytest.mark.parametrize(
    "smiles, exp_diester, exp_half, exp_diacid, exp_total, rationale",
    [
        # 1) Dimethyl malonate: classic malonate diester (CH2(CO2Me)2)
        (
            "COC(=O)CC(=O)OC",
            1, 0, 0, 1,
            "Dimethyl malonate: central CH2 bonded to two ester carbonyl carbons => diester=1, total=1.",
        ),
        # 2) Diethyl malonate: same motif, different OR
        (
            "CCOC(=O)CC(=O)OCC",
            1, 0, 0, 1,
            "Diethyl malonate: CH2(CO2Et)2 => diester=1.",
        ),
        # 3) Mixed diester: methyl ethyl malonate
        (
            "COC(=O)CC(=O)OCC",
            1, 0, 0, 1,
            "Mixed malonate diester: still two ester sides => diester=1.",
        ),
        # 4) Malonic acid: HOOC-CH2-COOH => diacid
        (
            "O=C(O)CC(=O)O",
            0, 0, 1, 1,
            "Malonic acid: central CH2 bonded to two carboxylic acid groups => diacid=1.",
        ),
        # 5) Malonic acid mono-methyl ester: half-ester (acid + ester)
        (
            "COC(=O)CC(=O)O",
            0, 1, 0, 1,
            "Monomethyl malonate (malonic acid monoester): one ester side + one acid side => half=1.",
        ),
        # 6) Substituted malonate center: methyl malonate with alpha methyl (CH(CH3)(CO2Me)2)
        (
            "COC(=O)C(C)C(=O)OC",
            1, 0, 0, 1,
            "Substituted malonate: central carbon is CH with R=CH3, still bonded to two ester carbonyl carbons => diester=1.",
        ),
        # 7) More substituted: diethyl 2,2-dimethylmalonate (C(CH3)2(CO2Et)2)
        (
            "CCOC(=O)C(C)(C)C(=O)OCC",
            1, 0, 0, 1,
            "2,2-dimethylmalonate diester: central quaternary carbon bonded to two ester carbonyl carbons => diester=1.",
        ),
        # 8) Half-ester variant: ethyl hydrogen malonate
        (
            "CCOC(=O)CC(=O)O",
            0, 1, 0, 1,
            "Ethyl hydrogen malonate: one ester + one acid => half=1.",
        ),
        # 9) Two malonate centers (additivity) using two disconnected fragments in one RDKit Mol
        (
            "COC(=O)CC(=O)OC.COC(=O)CC(=O)OC",
            2, 0, 0, 2,
            "Two separate dimethyl malonate fragments: each has one malonate center => total=2, diester=2.",
        ),
        # 10) Near-miss control: diethyl succinate is NOT a malonate center
        (
            "CCOC(=O)CCC(=O)OCC",
            0, 0, 0, 0,
            "Succinate diester: no single carbon bonded to two carbonyl carbons; carbonyls are separated => total=0.",
        ),
    ],
)
def test_malonates_A(smiles, exp_diester, exp_half, exp_diacid, exp_total, rationale):
    m = _mol(smiles)
    diester, half, diacid, total = count_malonate_structures(m)

    assert (diester, half, diacid, total) == (exp_diester, exp_half, exp_diacid, exp_total), rationale
    assert total == diester + half + diacid, "Subtype buckets should partition total (one bucket per center). " + rationale