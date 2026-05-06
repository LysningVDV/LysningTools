"""Nitro, imine, and amide/lactam detection (nitrogen motif counters)."""

from typing import Set, Tuple
from rdkit import Chem

# Precompiled patterns (module-level)
_NITRO_PATT = Chem.MolFromSmarts(r"[N+](=O)[O-]")
_ISOCYANATE_PATT = Chem.MolFromSmarts(r"N=C=O")

def _is_carbonyl_carbon(mol: Chem.Mol, c_atom: Chem.Atom) -> bool:
    """True if c_atom is a carbonyl carbon (has a C=O)."""
    c_idx = c_atom.GetIdx()
    for nb in c_atom.GetNeighbors():
        if nb.GetAtomicNum() != 8:
            continue
        b = mol.GetBondBetweenAtoms(c_idx, nb.GetIdx())
        if b is not None and b.GetBondType() == Chem.BondType.DOUBLE:
            return True
    return False


def count_nitro_groups(mol: Chem.Mol) -> int:
    """Nitro group detection (counts one per nitro group)."""
    if mol is None or _NITRO_PATT is None:
        return 0
    return len(mol.GetSubstructMatches(_NITRO_PATT, uniquify=True))


def count_imines(mol: Chem.Mol) -> int:
    """
    Count imine bonds (C=N) as a bond/site count.

    Semantics:
    - Count C=N DOUBLE bonds where C is carbon (6) and N is nitrogen (7).
    - Include aromatic-carbon imines (aryl imines are counted),
      but exclude cases where the nitrogen itself is aromatic (pyridine-like).
    - Exclude carbonyl carbons (C=O): not an imine.
    - Exclude amide-like contexts: if the nitrogen is attached to any carbonyl carbon, do not count.
    - Exclude oximes (C=N–O): if the imine nitrogen has any oxygen neighbor (N–O), do not count.
    """
    if mol is None:
        return 0

    n = 0
    for b in mol.GetBonds():
        if b.GetBondType() != Chem.BondType.DOUBLE:
            continue

        a1, a2 = b.GetBeginAtom(), b.GetEndAtom()
        if {a1.GetAtomicNum(), a2.GetAtomicNum()} != {6, 7}:
            continue

        c = a1 if a1.GetAtomicNum() == 6 else a2
        n_atom = a2 if c is a1 else a1

        # Exclude aromatic nitrogens (pyridine-like, etc.)
        if n_atom.GetIsAromatic():
            continue

        # Exclude oximes / N-oxides: N has an O neighbor
        if any(nb.GetAtomicNum() == 8 for nb in n_atom.GetNeighbors()):
            continue

        # Exclude carbonyl carbon (C=O)
        if _is_carbonyl_carbon(mol, c):
            continue

        # Exclude amide-like neighborhood: N attached to any carbonyl carbon
        for nb in n_atom.GetNeighbors():
            if nb.GetAtomicNum() != 6:
                continue
            if _is_carbonyl_carbon(mol, nb):
                break
        else:
            # only executed if the loop did NOT break => not attached to carbonyl
            n += 1

    return n


def _find_carboxamide_sites(mol: Chem.Mol) -> Set[Tuple[int, int]]:
    """
    Internal: return set of (acyl_c_idx, n_idx) carboxamide sites.

    Carboxamide site definition (for AmideCount_Total / LactamCount):
    - Carbonyl carbon C (C=O)
    - Has exactly ONE single-bond nitrogen neighbor (C(=O)-N)
    - Has NO single-bond oxygen neighbor on that carbonyl carbon
        * excludes esters/lactones/carbamates/carbonates
    - Excludes urea-like carbonyls (N-C(=O)-N) by requiring exactly one N neighbor
    """
    if mol is None:
        return set()

    sites: Set[Tuple[int, int]] = set()

    for c in mol.GetAtoms():
        if c.GetAtomicNum() != 6:
            continue
        if not _is_carbonyl_carbon(mol, c):
            continue

        c_idx = c.GetIdx()

        # Exclude if carbonyl carbon has any single-bond oxygen neighbor (ester/lactone/carbamate/carbonate)
        for nb in c.GetNeighbors():
            if nb.GetAtomicNum() != 8:
                continue
            b = mol.GetBondBetweenAtoms(c_idx, nb.GetIdx())
            if b is not None and b.GetBondType() == Chem.BondType.SINGLE:
                break
        else:
            # Gather single-bond nitrogen neighbors
            n_neighbors = []
            for nb in c.GetNeighbors():
                if nb.GetAtomicNum() != 7:
                    continue
                b = mol.GetBondBetweenAtoms(c_idx, nb.GetIdx())
                if b is not None and b.GetBondType() == Chem.BondType.SINGLE:
                    n_neighbors.append(nb)

            # Carboxamide definition: exactly one N neighbor
            if len(n_neighbors) == 1:
                n_idx = n_neighbors[0].GetIdx()
                sites.add((c_idx, n_idx))

    return sites


def count_amides(mol: Chem.Mol) -> int:
    """
    Count carboxamides (excluding carbamates/urethanes and urea-like carbonyls).

    Output key: AmideCount_Total
    """
    return len(_find_carboxamide_sites(mol))


def count_lactams(mol: Chem.Mol) -> int:
    """
    Count lactams = cyclic carboxamides (subset of AmideCount_Total).

    Lactam definition:
    - A carboxamide site where the acyl C–N bond is in a ring.

    Output key: LactamCount
    """
    sites = _find_carboxamide_sites(mol)
    lact = 0
    for c_idx, n_idx in sites:
        b = mol.GetBondBetweenAtoms(c_idx, n_idx)
        if b is not None and b.IsInRing():
            lact += 1
    return lact


def count_amides_and_lactams(mol: Chem.Mol) -> Tuple[int, int]:
    """
    Backward-compatible helper returning (amide_total, lactam_count).

    Kept intentionally so existing aggregator/tests can continue to call a single function
    while the public API exposes separate counters.
    """
    return count_amides(mol), count_lactams(mol)

def _find_urea_sites(mol: Chem.Mol) -> Set[int]:
    """
    Internal: return set of carbonyl carbon indices that are urea-like.

    Urea site definition:
    - Carbonyl carbon C (C=O)
    - Has exactly TWO single-bond nitrogen neighbors (N-C(=O)-N)
    - Has NO single-bond oxygen neighbor on that carbonyl carbon
      (excludes carbamates/urethanes/carbonates and esters/lactones)
    """
    if mol is None:
        return set()

    sites: Set[int] = set()

    for c in mol.GetAtoms():
        if c.GetAtomicNum() != 6:
            continue
        if not _is_carbonyl_carbon(mol, c):
            continue

        c_idx = c.GetIdx()

        # Exclude if carbonyl carbon has any single-bond oxygen neighbor
        for nb in c.GetNeighbors():
            if nb.GetAtomicNum() != 8:
                continue
            b = mol.GetBondBetweenAtoms(c_idx, nb.GetIdx())
            if b is not None and b.GetBondType() == Chem.BondType.SINGLE:
                break
        else:
            # Count single-bond nitrogen neighbors
            n_neighbors = 0
            for nb in c.GetNeighbors():
                if nb.GetAtomicNum() != 7:
                    continue
                b = mol.GetBondBetweenAtoms(c_idx, nb.GetIdx())
                if b is not None and b.GetBondType() == Chem.BondType.SINGLE:
                    n_neighbors += 1

            if n_neighbors == 2:
                sites.add(c_idx)

    return sites


def count_ureas(mol: Chem.Mol) -> int:
    """
    Count urea carbonyl sites (N-C(=O)-N), excluding carbamates/urethanes.

    Output key: UreaCount
    """
    return len(_find_urea_sites(mol))

def _find_urethane_sites(mol: Chem.Mol) -> Set[int]:
    """
    Internal: return set of carbonyl carbon indices that are urethane/carbamate-like.

    Urethane (carbamate) site definition:
    - Carbonyl carbon C (C=O)
    - Has at least one single-bond oxygen neighbor (C–O single)
    - Has at least one single-bond nitrogen neighbor (C–N single)
    - Counts one per carbonyl carbon
    """
    if mol is None:
        return set()

    sites: Set[int] = set()

    for c in mol.GetAtoms():
        if c.GetAtomicNum() != 6:
            continue
        if not _is_carbonyl_carbon(mol, c):
            continue

        c_idx = c.GetIdx()

        has_single_o = False
        has_single_n = False

        for nb in c.GetNeighbors():
            b = mol.GetBondBetweenAtoms(c_idx, nb.GetIdx())
            if b is None or b.GetBondType() != Chem.BondType.SINGLE:
                continue
            if nb.GetAtomicNum() == 8:
                has_single_o = True
            elif nb.GetAtomicNum() == 7:
                has_single_n = True

        if has_single_o and has_single_n:
            sites.add(c_idx)

    return sites


def count_urethanes(mol: Chem.Mol) -> int:
    """
    Count urethane/carbamate carbonyl sites (O-C(=O)-N).

    Output key: UrethaneCount
    """
    return len(_find_urethane_sites(mol))

def count_isocyanates(mol: Chem.Mol) -> int:
    """
    Count isocyanate groups (N=C=O).

    Output key: IsocyanateCount
    """
    if mol is None or _ISOCYANATE_PATT is None:
        return 0
    return len(mol.GetSubstructMatches(_ISOCYANATE_PATT, uniquify=True))