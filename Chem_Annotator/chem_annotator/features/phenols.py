"""Phenol subclass markers (perfumery-oriented)."""

from rdkit import Chem


def _ring_atoms_for_aromatic_atom(mol: Chem.Mol, aromatic_atom_idx: int) -> set:
    """
    Return atom indices of one ring containing the given aromatic atom.
    In fused systems, chooses the first matching ring (acceptable for class markers).
    """
    ring_info = mol.GetRingInfo()
    for r in ring_info.AtomRings():
        if aromatic_atom_idx in r:
            return set(r)
    return set()


def count_alkyl_phenols(mol: Chem.Mol) -> int:
    """
    Count alkyl-phenol OH sites (class marker).

    Definition:
    - A phenolic OH site (oxygen attached to an aromatic carbon in a ring)
    - where the same aromatic ring bears >= 1 alkyl substituent:
      an sp3 carbon neighbor (non-aromatic carbon) attached to any ring atom.

    Counts OH sites (one per phenolic oxygen).
    """
    if mol is None:
        return 0

    n = 0
    for o in mol.GetAtoms():
        if o.GetAtomicNum() != 8:
            continue

        # Find aromatic ring carbon neighbor (phenolic attachment point)
        aromatic_c = None
        for nb in o.GetNeighbors():
            if nb.GetAtomicNum() == 6 and nb.GetIsAromatic() and nb.IsInRing():
                aromatic_c = nb
                break
        if aromatic_c is None:
            continue

        ring_atoms = _ring_atoms_for_aromatic_atom(mol, aromatic_c.GetIdx())
        if not ring_atoms:
            continue

        # Ring has an alkyl substituent if any ring atom has a non-aromatic carbon neighbor
        ring_has_alkyl = False
        for ridx in ring_atoms:
            ra = mol.GetAtomWithIdx(ridx)
            for nbr in ra.GetNeighbors():
                if nbr.GetAtomicNum() == 6 and (not nbr.GetIsAromatic()):
                    ring_has_alkyl = True
                    break
            if ring_has_alkyl:
                break

        if ring_has_alkyl:
            n += 1

    return n