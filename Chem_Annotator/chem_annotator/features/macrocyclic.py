"""Macrocyclic musk descriptors."""
from typing import Tuple
from rdkit import Chem


def count_macrocyclic_musks(mol: Chem.Mol) -> Tuple[int, int, int]:
    """
    Return (macro_total, macro_ketones, macro_lactones) for macrocyclic "musk-like" motifs.

    Macro ring definition:
    - A macro ring is any ring with >= 12 atoms as reported by RDKit ring perception. [4](https://lysninginnovationconsultant-my.sharepoint.com/personal/villeneuve_lysning_nl/Documents/Microsoft%20Copilot%20Chat%20Files/macrocyclic.py)

    Per-ring counting:
    - macro_total: number of macro rings that contain EITHER a qualifying ketone OR a qualifying lactone.
    - macro_ketones: number of macro rings containing at least one qualifying ketone carbonyl.
    - macro_lactones: number of macro rings containing at least one qualifying lactone motif.

    Ketone (macro_ketones) semantics:
    - Carbonyl carbon (C=O) must be IN the macro ring.
    - Excludes ester-like carbonyls: if the same carbonyl carbon has ANY single-bond oxygen neighbor,
      it is treated as ester/lactone/carbonate-like and NOT counted as a ketone here. [4](https://lysninginnovationconsultant-my.sharepoint.com/personal/villeneuve_lysning_nl/Documents/Microsoft%20Copilot%20Chat%20Files/macrocyclic.py)

    Lactone (macro_lactones) semantics:
    - Matches the motif C(=O)O where BOTH:
        * the acyl carbon is in the macro ring, AND
        * the alkoxy oxygen is in the macro ring.
      This corresponds to an in-ring lactone closure. 

    Notes:
    - Counting is per macro ring set; fused systems may contribute multiple rings depending on RDKit's
      ring decomposition.
    """

    ri = mol.GetRingInfo()
    macro_total = macro_ket = macro_lac = 0
    atom_rings = ri.AtomRings()
    ring_sets = [set(r) for r in atom_rings if len(r) >= 12]
    if not ring_sets:
        return 0, 0, 0

    lactone_patt = Chem.MolFromSmarts("C(=O)O")

    for r in ring_sets:
        has_ket = False
        has_lac = False

        # --- ketones (exclude lactones/esters) ---
        # Carbonyl oxygen is exocyclic; require carbonyl carbon to be in the macro ring.
        # Exclude ester-like carbonyls by requiring NO single-bond O attached to the carbonyl carbon.
        for idx in r:
            c = mol.GetAtomWithIdx(idx)
            if c.GetAtomicNum() != 6:
                continue

            # carbonyl O? (C=O)
            has_c_double_o = any(
                b.GetBondType() == Chem.BondType.DOUBLE and nb.GetAtomicNum() == 8
                for nb in c.GetNeighbors()
                for b in [mol.GetBondBetweenAtoms(c.GetIdx(), nb.GetIdx())]
                if b is not None
            )
            if not has_c_double_o:
                continue

            # ester-like? (C–O single bond on the same carbonyl carbon)
            has_c_single_o = any(
                b.GetBondType() == Chem.BondType.SINGLE and nb.GetAtomicNum() == 8
                for nb in c.GetNeighbors()
                for b in [mol.GetBondBetweenAtoms(c.GetIdx(), nb.GetIdx())]
                if b is not None
            )

            if not has_c_single_o:
                has_ket = True
                break

        # --- lactones ---
        if lactone_patt is not None:
            for m_ in mol.GetSubstructMatches(lactone_patt, uniquify=True):
                acyl_c = m_[0]
                o_alk = m_[2]
                if acyl_c in r and o_alk in r:
                    has_lac = True
                    break

        if has_ket or has_lac:
            macro_total += 1
            macro_ket += int(has_ket)
            macro_lac += int(has_lac)

    return macro_total, macro_ket, macro_lac