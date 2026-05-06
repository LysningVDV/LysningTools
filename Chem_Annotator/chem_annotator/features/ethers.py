"""Ether related descriptors."""
from rdkit import Chem


def _is_ester_like_alkoxy_oxygen(o: Chem.Atom) -> bool:
    """
    True if this oxygen (degree-2) is bonded to a carbonyl carbon (i.e., part of an ester/lactone/carbonate-like motif).
    We treat such oxygens as NOT ethers for descriptor counting.
    """
    nbrs = o.GetNeighbors()
    for c in nbrs:
        if c.GetAtomicNum() != 6:
            continue
        # If carbon has a C=O double bond to oxygen (not the current oxygen), it's ester-like.
        for b in c.GetBonds():
            if b.GetBondType() == Chem.BondType.DOUBLE:
                other = b.GetOtherAtom(c)
                if other.GetAtomicNum() == 8 and other.GetIdx() != o.GetIdx():
                    return True
    return False


def count_ethers_excluding_esters(mol: Chem.Mol) -> int:
    """Count total R–O–R' ethers (including cyclic ethers and epoxides), excluding ester-like oxygens."""
    if mol is None:
        return 0

    cnt = 0
    for o in mol.GetAtoms():
        if o.GetAtomicNum() != 8 or o.GetDegree() != 2:
            continue
        nbrs = o.GetNeighbors()
        if not all(n.GetAtomicNum() == 6 for n in nbrs):
            continue
        if _is_ester_like_alkoxy_oxygen(o):
            continue
        cnt += 1
    return cnt


def ether_category_counts(mol: Chem.Mol) -> dict:
    """
    Return separate ether categories:
      - EtherCount_Total:   all ethers (acyclic + cyclic), excluding ester-like oxygens
      - EtherCount_Acyclic: ethers where oxygen is NOT in a ring
      - EtherCount_Cyclic:  ethers where oxygen IS in a ring (includes epoxides)
      - EpoxideCount:       cyclic ethers in a 3-membered ring
    """
    keys = {
        "EtherCount_Total": 0,
        "EtherCount_Acyclic": 0,   # previously “Linear”
        "EtherCount_Cyclic": 0,
        "EpoxideCount": 0,
    }
    if mol is None:
        return keys

    for o in mol.GetAtoms():
        if o.GetAtomicNum() != 8 or o.GetDegree() != 2:
            continue
        nbrs = o.GetNeighbors()
        if not all(n.GetAtomicNum() == 6 for n in nbrs):
            continue
        if _is_ester_like_alkoxy_oxygen(o):
            continue

        keys["EtherCount_Total"] += 1

        if o.IsInRing():
            keys["EtherCount_Cyclic"] += 1
            if o.IsInRingSize(3):
                keys["EpoxideCount"] += 1
        else:
            keys["EtherCount_Acyclic"] += 1

    return keys