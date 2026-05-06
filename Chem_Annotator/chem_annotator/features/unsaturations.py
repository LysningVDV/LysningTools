"""Unsaturation related descriptors."""

from rdkit import Chem
from ..utils import count_unsaturated_bonds  # legacy: includes aromatic + hetero-atom unsaturation


def count_cc_unsaturated_bonds(mol: Chem.Mol) -> int:
    """
    Count *strict* carbon–carbon unsaturation bonds.

    Semantics:
    - Counts only bonds where BOTH atoms are carbon (atomic number 6).
    - Aromatic C–C bonds each contribute 1 to the count.
    - Non-aromatic C–C DOUBLE and TRIPLE bonds each contribute 1.
    - Does NOT count hetero-atom unsaturation (e.g., C=O, S=O, N=O).
    - Intended for 'NumUnsaturatedBonds' used by 'IsFullySaturated'.
    """
    n = 0
    for b in mol.GetBonds():
        a1, a2 = b.GetBeginAtom(), b.GetEndAtom()
        if a1.GetAtomicNum() == 6 and a2.GetAtomicNum() == 6:
            if b.GetIsAromatic():
                n += 1
            elif b.GetBondType() in (Chem.BondType.DOUBLE, Chem.BondType.TRIPLE):
                n += 1
    return n


def count_cc_alkene_bonds(mol: Chem.Mol) -> int:
    """
    Count carbon–carbon alkene bonds (C=C) excluding aromatic bonds.

    Semantics:
    - Counts only C–C DOUBLE bonds that are NOT aromatic.
    - Aromatic bonds do not contribute to this counter.
    """
    n = 0
    for b in mol.GetBonds():
        if b.GetIsAromatic():
            continue
        if b.GetBondType() != Chem.BondType.DOUBLE:
            continue
        a1, a2 = b.GetBeginAtom(), b.GetEndAtom()
        if a1.GetAtomicNum() == 6 and a2.GetAtomicNum() == 6:
            n += 1
    return n


def count_cc_alkyne_bonds(mol: Chem.Mol) -> int:
    """
    Count carbon–carbon alkyne bonds (C#C).

    Semantics:
    - Counts only C–C TRIPLE bonds.
    """
    n = 0
    for b in mol.GetBonds():
        if b.GetBondType() != Chem.BondType.TRIPLE:
            continue
        a1, a2 = b.GetBeginAtom(), b.GetEndAtom()
        if a1.GetAtomicNum() == 6 and a2.GetAtomicNum() == 6:
            n += 1
    return n