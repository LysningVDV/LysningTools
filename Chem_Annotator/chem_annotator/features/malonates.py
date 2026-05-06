"""Malonate structures."""
from typing import Tuple
from rdkit import Chem

def count_malonate_structures(mol: Chem.Mol) -> Tuple[int, int, int, int]:
    """
    Detect malonate-like centers: CH(R)(COOX)(COOX').

    Operational definition:
    - We scan carbon atoms and look for two neighboring carbonyl carbons connected by single bonds
      (a malonate backbone center).
    - Each side must be a carbonyl carbon (C=O) with a single-bond oxygen substituent.

    Side classification:
    - "ester": carbonyl carbon has a single-bond oxygen that is substituted as OR (oxygen bonded to a carbon).
    - "acid": carbonyl carbon has a single-bond oxygen with >=1 hydrogen (neutral –C(=O)OH).

    Important semantics:
    - Carboxylates (–C(=O)O⁻) are NOT classified as "acid" here because the oxygen has 0 hydrogens.
      They therefore do not contribute to the "diacid" or "half-ester" acid side counts. [2](https://lysninginnovationconsultant-my.sharepoint.com/personal/villeneuve_lysning_nl/Documents/Microsoft%20Copilot%20Chat%20Files/malonates.py)

    Returns:
        (diester, half_ester, diacid, total)
        - diester: both sides are esters
        - half_ester: one ester + one acid
        - diacid: both sides are neutral acids
        - total: total malonate-like centers found (unique central carbon sites) [2](https://lysninginnovationconsultant-my.sharepoint.com/personal/villeneuve_lysning_nl/Documents/Microsoft%20Copilot%20Chat%20Files/malonates.py)
    """

    diester = half = diacid = total = 0
    visited = set()

    for c in mol.GetAtoms():
        if c.GetAtomicNum() != 6:
            continue
        c_idx = c.GetIdx()

        # gather carboxyl-type neighbors
        sides = []

        for nb in c.GetNeighbors():
            if nb.GetAtomicNum() != 6: 
                continue

            b_cn = mol.GetBondBetweenAtoms(c_idx, nb.GetIdx())
            if not b_cn or b_cn.GetBondType() != Chem.BondType.SINGLE:
                continue

            # carbonyl?
            carbonyl_O = None
            for b in nb.GetBonds():
                if b.GetBondType() == Chem.BondType.DOUBLE and \
                   b.GetOtherAtom(nb).GetAtomicNum() == 8:
                    carbonyl_O = b.GetOtherAtom(nb).GetIdx()
                    break
            if carbonyl_O is None:
                continue

            # single-bond O substituent?
            o_type = None
            for nb2 in nb.GetNeighbors():
                if nb2.GetIdx() in (c_idx, carbonyl_O):
                    continue
                if nb2.GetAtomicNum() == 8:
                    b_no = mol.GetBondBetweenAtoms(nb.GetIdx(), nb2.GetIdx())
                    if b_no and b_no.GetBondType() == Chem.BondType.SINGLE:
                        if nb2.GetTotalNumHs() >= 1:
                            o_type = "acid"
                        else:
                            # OR?
                            if any(n3.GetAtomicNum() == 6 and n3.GetIdx() != nb.GetIdx()
                                   for n3 in nb2.GetNeighbors()):
                                o_type = "ester"
                        break

            if o_type is not None:
                sides.append(o_type)

        if len(sides) == 2:
            if c_idx in visited:
                continue
            visited.add(c_idx)
            total += 1
            s = tuple(sorted(sides))
            if s == ("ester", "ester"):
                diester += 1
            elif "acid" in s and "ester" in s:
                half += 1
            elif s == ("acid", "acid"):
                diacid += 1

    return diester, half, diacid, total

