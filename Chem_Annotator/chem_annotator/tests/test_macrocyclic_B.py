import pytest
from rdkit import Chem

from chem_annotator.features.macrocyclic import count_macrocyclic_musks


def _mol(smiles: str) -> Chem.Mol:
    m = Chem.MolFromSmiles(smiles)
    assert m is not None, f"RDKit failed to parse SMILES: {smiles}"
    return m


# Overlap rules (explicit):
# - macro_total counts macro rings (>=12 atoms) that contain a ketone OR a lactone (per ring).
# - macro_ketones counts macro rings containing at least one ketone carbonyl in-ring.
#   IMPORTANT: lactone/ester carbonyls do NOT count as ketones.
# - macro_lactones counts macro rings containing an in-ring lactone motif C(=O)O
#   with both the acyl carbon and the alkoxy oxygen in the macro ring.
# - A macrocycle can in principle contain both a ketone and a lactone (different carbonyl sites);
#   then both macro_ketones and macro_lactones may increment (allowed multi-count across buckets).


@pytest.mark.parametrize(
    "smiles, exp_total, exp_ket, exp_lac, rationale",
    [
        # 1) Cyclododecanone: 12-member ring with ketone => total=1, ket=1, lac=0
        (
            "O=C1CCCCCCCCCCC1",
            1, 1, 0,
            "Cyclododecanone: macro ring (12 atoms) with a ketone carbonyl; not an ester/lactone => ketone-positive only.",
        ),

        # 2) Cyclopentadecanone: 15-member ring ketone => total=1, ket=1, lac=0
        (
            "O=C1CCCCCCCCCCCCCC1",
            1, 1, 0,
            "Cyclopentadecanone: macro ring (>=12) with ketone carbonyl => counted as macro ketone.",
        ),

        # 3) Macro lactone: should be lactone-positive but NOT ketone-positive
        # Example: 1-oxacyclotridecan-2-one (macro lactone)
        (
            "O=C1OCCCCCCCCCCCC1",
            1, 0, 1,
            "Macro lactone: ring contains C(=O)O with acyl carbon and ring oxygen in-ring => lactone-positive. "
            "Ester carbonyl must NOT be counted as ketone.",
        ),

        # 4) Larger macro lactone: same logic
        (
            "O=C1OCCCCCCCCCCCCC1",
            1, 0, 1,
            "Macro lactone (larger ring): lactone-positive; ester carbonyl excluded from ketone bucket.",
        ),

        # 5) Macro ketone with exocyclic ester substituent: lactone should remain 0
        (
            "O=C1CCCCCCCCCCC1OC(=O)C",
            1, 1, 0,
            "Macro ketone ring present. Ester is exocyclic: acyl carbon is not in the macro ring, so lactone condition fails.",
        ),

        # 6) Macrocycle without carbonyls: should be 0,0,0 (core boundary control)
        (
            "C1CCCCCCCCCCC1",
            0, 0, 0,
            "Cyclododecane: macro ring present but no ketone or lactone motif => not counted by macro musk indicator.",
        ),

        # 7) 11-member lactone (below threshold): excluded even though lactone motif exists
        (
            "O=C1OCCCCCCCCC1",
            0, 0, 0,
            "Lactone present but ring size <12 => excluded by macro ring size threshold.",
        ),

        # 8) 11-member ketone (below threshold): excluded
        (
            "O=C1CCCCCCCCCC1",
            0, 0, 0,
            "Ketone present but ring size 11 => excluded by macro ring size threshold.",
        ),
    ],
)
def test_macrocyclic_A(smiles, exp_total, exp_ket, exp_lac, rationale):
    m = _mol(smiles)
    got_total, got_ket, got_lac = count_macrocyclic_musks(m)
    assert (got_total, got_ket, got_lac) == (exp_total, exp_ket, exp_lac), rationale