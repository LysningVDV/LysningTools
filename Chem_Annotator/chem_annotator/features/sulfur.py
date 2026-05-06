"""Sulfur containing descriptors."""
from typing import Tuple
from rdkit import Chem

def count_thiols(mol: Chem.Mol) -> int:
    """Count S–H attached to carbon."""
    n = 0
    for s in mol.GetAtoms():
        if s.GetAtomicNum() == 16 and s.GetTotalNumHs() >= 1:
            if any(nb.GetAtomicNum() == 6 for nb in s.GetNeighbors()):
                n += 1
    return n

def count_aliphatic_thiols(mol: Chem.Mol) -> int:
    """S–H attached to non-aromatic carbon."""
    n = 0
    for s in mol.GetAtoms():
        if s.GetAtomicNum() == 16 and s.GetTotalNumHs() >= 1:
            if any(nb.GetAtomicNum() == 6 and not nb.GetIsAromatic()
                   for nb in s.GetNeighbors()):
                n += 1
    return n

def count_thiophenols(mol: Chem.Mol) -> int:
    """S–H on an aromatic carbon."""
    n = 0
    for s in mol.GetAtoms():
        if s.GetAtomicNum() == 16 and s.GetTotalNumHs() >= 1:
            if any(nb.GetAtomicNum() == 6 and nb.GetIsAromatic()
                   for nb in s.GetNeighbors()):
                n += 1
    return n

def count_disulfides(mol: Chem.Mol) -> int:
    """R–S–S–R'."""
    cnt = 0
    for b in mol.GetBonds():
        if (b.GetBeginAtom().GetAtomicNum() == 16 and
            b.GetEndAtom().GetAtomicNum() == 16):
            cnt += 1
    return cnt

def count_thioesters(mol: Chem.Mol) -> int:
    """R–C(=O)–S–R'."""
    cnt = 0
    for c in mol.GetAtoms():
        if c.GetAtomicNum() != 6:
            continue
        # carbonyl?
        has_c_eq_o = False
        for b in c.GetBonds():
            if b.GetBondType() == Chem.BondType.DOUBLE and \
               b.GetOtherAtom(c).GetAtomicNum() == 8:
                has_c_eq_o = True
                break
        if not has_c_eq_o:
            continue
        # sulfur single-bond neighbor?
        for nb in c.GetNeighbors():
            if nb.GetAtomicNum() == 16:
                b = mol.GetBondBetweenAtoms(c.GetIdx(), nb.GetIdx())
                if b and b.GetBondType() == Chem.BondType.SINGLE and nb.GetDegree() == 2:
                    cnt += 1
                    break
    return cnt

def count_thioethers_excluding_thioesters(mol: Chem.Mol) -> int:
    """Count R–S–R', excluding thioesters."""
    cnt = 0
    for s in mol.GetAtoms():
        if s.GetAtomicNum() == 16 and s.GetDegree() == 2:
            nbrs = s.GetNeighbors()
            if all(nb.GetAtomicNum() == 6 for nb in nbrs):
                # check for thioester-like pattern
                thioester_like = False
                for c in nbrs:
                    for b in c.GetBonds():
                        if b.GetBondType() == Chem.BondType.DOUBLE and \
                           b.GetOtherAtom(c).GetAtomicNum() == 8:
                            thioester_like = True
                            break
                    if thioester_like:
                        break
                if not thioester_like:
                    cnt += 1
    return cnt


def count_sulfoxides(mol: Chem.Mol) -> int:
    # X3 ensures sulfur has exactly one =O and two single-bond substituents (excludes sulfones, which are X4).
    patt = Chem.MolFromSmarts("[S;X3](=O)([#6])[#6]")
    return 0 if patt is None else len(mol.GetSubstructMatches(patt, uniquify=True))


def count_sulfones(mol: Chem.Mol) -> int:
    patt = Chem.MolFromSmarts("S(=O)(=O)([#6])[#6]")
    return 0 if patt is None else len(mol.GetSubstructMatches(patt, uniquify=True))


# ---------------------------------------------------------------------------
# THIOPHENOL POSITIONAL ISOMERS (o / m / p)
# ---------------------------------------------------------------------------

def classify_thiophenol_positions(mol: Chem.Mol) -> Tuple[int, int, int]:
    """Return (#ortho, #meta, #para) positional substituted thiophenols."""
    ortho = meta = para = 0
    ring_info = mol.GetRingInfo()

    for s in mol.GetAtoms():
        if s.GetAtomicNum() != 16 or s.GetTotalNumHs() < 1:
            continue

        c_ar = None
        for nb in s.GetNeighbors():
            if nb.GetAtomicNum() == 6 and nb.GetIsAromatic():
                c_ar = nb
                break
        if c_ar is None or not c_ar.IsInRing():
            continue

        ring = None
        for r in ring_info.AtomRings():
            if c_ar.GetIdx() in r:
                ring = list(r)
                break
        if ring is None:
            continue

        start = ring.index(c_ar.GetIdx())
        ordered = ring[start:] + ring[:start]
        N = len(ordered)

        def substituted(idx):
            a = mol.GetAtomWithIdx(idx)
            for nb in a.GetNeighbors():
                if nb.GetIdx() not in ring and nb.GetAtomicNum() != 1:
                    return True
            return False

        # positions
        o_pos = {ordered[(0 + 1) % N], ordered[(0 - 1) % N]}
        m_pos = {ordered[(0 + 2) % N], ordered[(0 - 2) % N]}
        p_pos = {ordered[(0 + 3) % N], ordered[(0 - 3) % N]} if N >= 6 else set()

        if any(substituted(i) for i in o_pos):
            ortho += 1
        elif any(substituted(i) for i in m_pos):
            meta += 1
        elif any(i in p_pos and substituted(i) for i in p_pos):
            para += 1

    return ortho, meta, para
