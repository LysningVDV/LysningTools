"""Halogen related descriptors."""
from rdkit import Chem

# Atomic numbers: F=9, Cl=17, Br=35, I=53
HALO_ATOMICNUMS = {9: "F", 17: "Cl", 35: "Br", 53: "I"}
HALO_SET = set(HALO_ATOMICNUMS.keys())


# ----------------------------
# 1) Halogen atom counts
# ----------------------------
def count_halogen_atoms_total(mol: Chem.Mol) -> int:
    """Total number of halogen atoms (F/Cl/Br/I) in the molecule."""
    return sum(1 for a in mol.GetAtoms() if a.GetAtomicNum() in HALO_SET)


def count_halogen_atoms_by_halogen(mol: Chem.Mol) -> dict:
    """Number of halogen atoms by type (F/Cl/Br/I)."""
    out = {f"HalogenAtomCount_{lbl}": 0 for lbl in HALO_ATOMICNUMS.values()}
    for a in mol.GetAtoms():
        anum = a.GetAtomicNum()
        if anum in HALO_ATOMICNUMS:
            out[f"HalogenAtomCount_{HALO_ATOMICNUMS[anum]}"] += 1
    return out


# ----------------------------
# 2) Halogenated carbon sites
# ----------------------------
def count_halogenated_carbons(mol: Chem.Mol) -> int:
    """Any carbon directly bonded to F/Cl/Br/I (carbon-site counting).

    Each carbon atom is counted once if it has >=1 halogen neighbor,
    regardless of how many halogens are attached.
    """
    cnt = 0
    for c in mol.GetAtoms():
        if c.GetAtomicNum() != 6:
            continue
        if any(nb.GetAtomicNum() in HALO_SET for nb in c.GetNeighbors()):
            cnt += 1
    return cnt


def count_halogenated_carbons_by_halogen(mol: Chem.Mol) -> dict:
    """Carbon atoms directly bonded to F/Cl/Br/I, returned per halogen type.

    Marker-style overlap:
    - A carbon bonded to multiple halogen TYPES increments multiple buckets.
    - Still carbon-site based within each bucket (a carbon counts once per halogen type).
    """
    out = {f"HalogenatedCarbonCount_{lbl}": 0 for lbl in HALO_ATOMICNUMS.values()}

    for c in mol.GetAtoms():
        if c.GetAtomicNum() != 6:
            continue

        present = set()
        for nb in c.GetNeighbors():
            anum = nb.GetAtomicNum()
            if anum in HALO_ATOMICNUMS:
                present.add(HALO_ATOMICNUMS[anum])

        for lbl in present:
            out[f"HalogenatedCarbonCount_{lbl}"] += 1

    return out


def count_halogenated_carbons_by_halogen_split_aromatic(mol: Chem.Mol) -> dict:
    """Halogenated carbon sites by halogen type, split into aromatic vs aliphatic carbons.

    Useful because aryl halides and alkyl halides often behave differently in models.
    Marker-style overlap across halogen types is allowed.
    """
    out = {}
    for lbl in HALO_ATOMICNUMS.values():
        out[f"HalogenatedArylCarbonCount_{lbl}"] = 0
        out[f"HalogenatedAlkylCarbonCount_{lbl}"] = 0

    for c in mol.GetAtoms():
        if c.GetAtomicNum() != 6:
            continue

        present = set()
        for nb in c.GetNeighbors():
            anum = nb.GetAtomicNum()
            if anum in HALO_ATOMICNUMS:
                present.add(HALO_ATOMICNUMS[anum])

        if not present:
            continue

        is_aryl = bool(c.GetIsAromatic())
        for lbl in present:
            key = "HalogenatedArylCarbonCount_" if is_aryl else "HalogenatedAlkylCarbonCount_"
            out[f"{key}{lbl}"] += 1

    return out


# ----------------------------
# 3) Halophenols (phenolic OH on a halogenated aromatic ring)
# ----------------------------
def _ring_atoms_for_aromatic_atom(mol: Chem.Mol, aromatic_atom_idx: int) -> set:
    """Return the atom indices of one ring containing the given aromatic atom index.

    Note: In fused systems, an atom can be in multiple rings; this chooses the first match.
    For halophenol classification this is typically acceptable; refine if needed later.
    """
    ring_info = mol.GetRingInfo()
    for r in ring_info.AtomRings():
        if aromatic_atom_idx in r:
            return set(r)
    return set()


def count_halogenated_phenols(mol: Chem.Mol) -> int:
    """
    Count halophenol *sites* (class marker).

    Definition:
    - A "halophenol site" is a phenolic OH (oxygen with an aromatic carbon neighbor in a ring)
      where that same aromatic ring has ≥1 halogen substituent (F/Cl/Br/I) on any ring atom.

    Semantics:
    - Counts OH *sites* (one per phenolic oxygen), not the number of halogens.
    - Intended as a coarse class indicator (presence/degree of halophenolic character),
      not a detailed reactivity predictor. """
    n = 0
    for o in mol.GetAtoms():
        if o.GetAtomicNum() != 8:
            continue

        # Find an aromatic carbon neighbor in a ring (phenolic attachment point)
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

        # Correct logic: halogens are substituents on ring atoms, not ring members
        ring_has_halogen = False
        for ridx in ring_atoms:
            ra = mol.GetAtomWithIdx(ridx)
            if any(nbr.GetAtomicNum() in HALO_SET for nbr in ra.GetNeighbors()):
                ring_has_halogen = True
                break

        if ring_has_halogen:
            n += 1

    return n



def count_halogenated_phenols_by_halogen(mol: Chem.Mol) -> dict:
    """
    Count halophenol OH *sites* per halogen type present on the same aromatic ring.

    Marker-style overlap semantics:
    - If the ring contains multiple halogen TYPES (e.g., Cl and Br), the same OH site
      increments multiple buckets (HalogenatedPhenolCount_Cl and _Br).
    - Within each bucket, each OH site counts once, regardless of how many substituents
      of that halogen type are present on the ring."""

    out = {f"HalogenatedPhenolCount_{lbl}": 0 for lbl in HALO_ATOMICNUMS.values()}

    for o in mol.GetAtoms():
        if o.GetAtomicNum() != 8:
            continue

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

        present = set()
        for ridx in ring_atoms:
            ra = mol.GetAtomWithIdx(ridx)
            for nbr in ra.GetNeighbors():
                anum = nbr.GetAtomicNum()
                if anum in HALO_ATOMICNUMS:
                    present.add(HALO_ATOMICNUMS[anum])

        for lbl in present:
            out[f"HalogenatedPhenolCount_{lbl}"] += 1

    return out