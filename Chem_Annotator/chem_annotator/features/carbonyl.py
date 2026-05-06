"""Carbonyl related feature extraction."""
from typing import Tuple
from rdkit import Chem
from ..utils import get_ring_sets
from ..chem_patterns import ESTER_PATT


def count_lactones_split(mol: Chem.Mol) -> Tuple[int, int, int]:
    """Return lactone_count, open_ester_count, ester_total.

    Ester/lactone site definition (functional-group convention):
    - A carbonyl carbon C with a double-bond O (C=O) and a single-bond O that is not protonated (O has H0).
    - Excludes carboxylic acids (C(=O)OH).
    - Excludes anhydrides by requiring the single-bond O not to be bonded to another carbonyl carbon.

    Note:
    - Some aromatic lactones (e.g., coumarin) may have the acyl C–O bond perceived as AROMATIC by RDKit.
      For ester-site discovery, we treat SINGLE and AROMATIC C–O bonds equivalently.
    """
    if mol is None:
        return 0, 0, 0

    # Keep behavior consistent with original dependency on ESTER_PATT:
    # if ester SMARTS failed to load, treat as no esters.
    if ESTER_PATT is None:
        return 0, 0, 0

    # Kept for compatibility / minimal change; not required for the final classification anymore.
    _ringsets = get_ring_sets(mol)

    sites = set()  # (acyl_c_idx, alkoxy_o_idx)

    for c in mol.GetAtoms():
        if c.GetAtomicNum() != 6:
            continue
        c_idx = c.GetIdx()

        # Identify carbonyl oxygen (double-bond O) and candidate alkoxy oxygens (single/aromatic-bond O, H0).
        has_carbonylo = False
        alkoxy_oxygens = []

        for bond in c.GetBonds():
            nbr = bond.GetOtherAtom(c)
            if nbr.GetAtomicNum() != 8:
                continue

            if bond.GetBondType() == Chem.BondType.DOUBLE:
                # C=O
                has_carbonylo = True

            elif bond.GetBondType() in (Chem.BondType.SINGLE, Chem.BondType.AROMATIC):
                # C-O where O is not protonated => excludes acids
                # Accept AROMATIC here to catch aromatic lactones such as coumarin.
                if nbr.GetTotalNumHs() == 0:
                    alkoxy_oxygens.append(nbr)

        if not has_carbonylo or not alkoxy_oxygens:
            continue

        # Add ester sites; exclude anhydrides: O bonded to another carbonyl carbon.
        for o in alkoxy_oxygens:
            # find the other neighbor of this oxygen besides the current carbonyl carbon
            other_neighbors = [n for n in o.GetNeighbors() if n.GetIdx() != c_idx]
            if not other_neighbors:
                continue
            other = other_neighbors[0]

            # If oxygen is attached to another carbonyl carbon, it's an anhydride-like linkage -> skip.
            if other.GetAtomicNum() == 6:
                other_is_carbonyl = any(
                    (b.GetBondType() == Chem.BondType.DOUBLE and b.GetOtherAtom(other).GetAtomicNum() == 8)
                    for b in other.GetBonds()
                )
                if other_is_carbonyl:
                    continue

            sites.add((c_idx, o.GetIdx()))

    if not sites:
        return 0, 0, 0

    # Lactone = ester where the acyl C–O bond is part of a ring closure.
    lact = 0
    for c_idx, o_idx in sites:
        b = mol.GetBondBetweenAtoms(c_idx, o_idx)
        if b is not None and b.IsInRing():
            lact += 1

    total = len(sites)
    return lact, total - lact, total