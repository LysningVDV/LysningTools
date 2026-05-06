"""Acetal, ketal, and orthoester detection (textbook definitions)."""

from typing import Tuple
from rdkit import Chem


def _is_carbonyl_carbon(mol: Chem.Mol, c_atom: Chem.Atom) -> bool:
    """True if carbon has a C=O double-bonded oxygen."""
    c_idx = c_atom.GetIdx()
    for nb in c_atom.GetNeighbors():
        if nb.GetAtomicNum() != 8:
            continue
        b = mol.GetBondBetweenAtoms(c_idx, nb.GetIdx())
        if b is not None and b.GetBondType() == Chem.BondType.DOUBLE:
            return True
    return False


def _is_or_oxygen(o_atom: Chem.Atom, center_c_idx: int) -> bool:
    """
    True if oxygen is 'OR-like' relative to the acetal center:
    - oxygen has no hydrogens (excludes OH)
    - oxygen is connected to at least one carbon besides the center carbon
    """
    if o_atom.GetAtomicNum() != 8:
        return False
    if o_atom.GetTotalNumHs() != 0:
        return False
    for nb in o_atom.GetNeighbors():
        if nb.GetIdx() == center_c_idx:
            continue
        if nb.GetAtomicNum() == 6:
            return True
    return False


def count_acetals_ketals_orthoesters(mol: Chem.Mol) -> Tuple[int, int, int]:
    """
    Return (acetal_count, ketal_count, orthoester_count).

    Textbook definitions:
    - Acetal/Ketal center = carbon atom with EXACTLY 2 OR-oxygen neighbors (O, H0, bonded to carbon),
      and carbon is not a carbonyl carbon.
    - Orthoester center = carbon atom with EXACTLY 3 OR-oxygen neighbors (same OR definition),
      and carbon is not a carbonyl carbon.

    Acetal vs ketal split (for the EXACTLY-2 case):
      * acetal: center carbon has >= 1 H
      * ketal: center carbon has 0 H

    Notes:
    - Cyclic acetals/ketals are included (e.g., 1,3-dioxolanes).
    - Each center carbon counts once.
    """
    if mol is None:
        return 0, 0, 0

    acetal = 0
    ketal = 0
    ortho = 0

    for c in mol.GetAtoms():
        if c.GetAtomicNum() != 6:
            continue
        if _is_carbonyl_carbon(mol, c):
            continue

        c_idx = c.GetIdx()

        # Count OR-like oxygen neighbors (single-bond only)
        or_oxygens = 0
        for nb in c.GetNeighbors():
            if nb.GetAtomicNum() != 8:
                continue
            b = mol.GetBondBetweenAtoms(c_idx, nb.GetIdx())
            if b is None or b.GetBondType() != Chem.BondType.SINGLE:
                continue
            if _is_or_oxygen(nb, c_idx):
                or_oxygens += 1

        if or_oxygens == 2:
            # acetal vs ketal split by H count on the center carbon
            if c.GetTotalNumHs() >= 1:
                acetal += 1
            else:
                ketal += 1
        elif or_oxygens == 3:
            ortho += 1

    return acetal, ketal, ortho


def count_acetals_and_ketals(mol: Chem.Mol) -> Tuple[int, int]:
    """
    Backward-compatible helper returning (acetal_count, ketal_count).

    Kept so existing code can continue to call the 2-tuple API if needed.
    """
    a, k, _o = count_acetals_ketals_orthoesters(mol)
    return a, k