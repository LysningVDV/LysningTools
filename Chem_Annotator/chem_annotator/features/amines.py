from __future__ import annotations

from typing import Tuple
from rdkit import Chem
from rdkit.Chem.rdchem import BondType


def _is_carbonyl_carbon(atom: Chem.Atom) -> bool:
    """Return True if atom is a carbonyl carbon (C=O or C=S)."""
    if atom.GetAtomicNum() != 6:
        return False
    for b in atom.GetBonds():
        if b.GetBondType() == BondType.DOUBLE:
            other = b.GetOtherAtom(atom)
            if other.GetAtomicNum() in (8, 16):  # O or S
                return True
    return False


def _is_sulfonyl_sulfur(atom: Chem.Atom) -> bool:
    """Return True if atom is a sulfonyl sulfur (S(=O)(=O)...)."""
    if atom.GetAtomicNum() != 16:
        return False
    dbl_o = 0
    for b in atom.GetBonds():
        if b.GetBondType() == BondType.DOUBLE and b.GetOtherAtom(atom).GetAtomicNum() == 8:
            dbl_o += 1
    return dbl_o >= 2


def _is_amine_nitrogen(n: Chem.Atom) -> bool:
    """
    Strict 'amine-like' nitrogen:
    - N is not aromatic
    - N has only single bonds (exclude N=*, N#*)
    - N is not attached to a carbonyl carbon (amide/urea/urethane/lactam/etc.)
    - N is not attached to sulfonyl sulfur (sulfonamide)
    """
    if n.GetAtomicNum() != 7:
        return False

    # Exclude aromatic nitrogens (pyridine, pyrazine, indole [nH], etc.)
    if n.GetIsAromatic():
        return False

    # Exclude any N with double or triple bonds (imines, nitriles, azo, nitro, etc.)
    for b in n.GetBonds():
        bt = b.GetBondType()
        if bt == BondType.DOUBLE or bt == BondType.TRIPLE:
            return False

    # Exclude amide-like N: attached to carbonyl carbon
    for nb in n.GetNeighbors():
        if _is_carbonyl_carbon(nb):
            return False

    # Exclude sulfonamides (common false positives in broad N counters)
    for nb in n.GetNeighbors():
        if _is_sulfonyl_sulfur(nb):
            return False

    return True


def classify_and_count_amines(m: Chem.Mol) -> Tuple[int, int, int, int]:
    """
    Return (primary, secondary, tertiary, total) strict amine counts.

    Classification is based on:
    - explicit/implicit H count on N
    - degree (number of neighbors)
    - allows protonated amines (e.g., [NH3+], [NH2+]) by mapping them to their
      neutral class (primary/secondary/tertiary) when reasonable.
    """
    primary = secondary = tertiary = 0

    for atom in m.GetAtoms():
        if not _is_amine_nitrogen(atom):
            continue

        deg = atom.GetDegree()                 # number of bonded neighbors
        h = atom.GetTotalNumHs()               # implicit + explicit H
        chg = atom.GetFormalCharge()

        # Neutral amines
        if chg == 0:
            if deg == 1 and h == 2:
                primary += 1
            elif deg == 2 and h == 1:
                secondary += 1
            elif deg == 3 and h == 0:
                tertiary += 1
            # else: ignore edge cases (e.g. unusual valence)
            continue

        # Protonated amines (common in some datasets)
        if chg == 1:
            if deg == 1 and h == 3:
                primary += 1
            elif deg == 2 and h == 2:
                secondary += 1
            elif deg == 3 and h == 1:
                tertiary += 1
            # Quaternary ammonium (deg==4, h==0) intentionally not counted here
            continue

        # Other charges are not treated as amines
        continue

    total = primary + secondary + tertiary
    return primary, secondary, tertiary, total