from typing import List, Optional
from rdkit import Chem
from .chem_patterns import (
    OH_PATT,
    EXCLUDE_ALPHA_HYDROXY_CARBONYLS,
    EXCLUDE_ENOLS,
    TRACK_EXCLUDED_IN_AUDIT,
)

# Optional configuration: whether enols should also be counted as alcohols (P/S/T).
# Strict IUPAC class logic recommends False; descriptor-overlap workflows may set True.
try:
    from .chem_patterns import COUNT_ENOLS_AS_ALCOHOLS
except Exception:  # pragma: no cover
    COUNT_ENOLS_AS_ALCOHOLS = False

# ---------- Oximes (C=N–OH) ----------
# Imine-bound hydroxyls (oximes) must be excluded from alcohol counts,
# but tracked separately via OximeCount.
# ---------- Oximes (C=N–OH or N=C–OH) ----------
# Detect both orientations separately.
OXIME_PATTERNS = [
    Chem.MolFromSmarts("[C]=[N]-[OX2H]"),  # C=N–OH
    Chem.MolFromSmarts("[N]=[C]-[OX2H]"),  # N=C–OH
]

def count_oxime_sites(mol):
    """
    Return:
        count,
        {o_idx: (n_idx, c_idx)} mapping for exclusion logic
    """
    o_to_nc = {}

    for patt in OXIME_PATTERNS:
        if patt is None:
            continue

        for match in mol.GetSubstructMatches(patt, uniquify=True):
            # match is (atom1, atom2, atom3) in SMARTS order
            a1, a2, o_idx = match

            # Normalise to (n_idx, c_idx, o_idx)
            if mol.GetAtomWithIdx(a1).GetAtomicNum() == 7:
                # N = C – O
                n_idx, c_idx = a1, a2
            else:
                # C = N – O
                c_idx, n_idx = a1, a2

            o_to_nc[o_idx] = (n_idx, c_idx)

    return len(o_to_nc), o_to_nc

# ---------- Core predicates ----------
def is_alpha_to_carbonyl(mol: Chem.Mol, c_idx: int, o_idx: int) -> bool:
    """Detect C(OH)–C(=O)X where the C=O oxygen is not our OH oxygen."""
    c = mol.GetAtomWithIdx(c_idx)
    for n in c.GetNeighbors():
        if n.GetAtomicNum() != 6:
            continue
        # look for C=O on the neighbor carbon
        for b in n.GetBonds():
            if b.GetBondType() != Chem.BondType.DOUBLE:
                continue
            other = b.GetOtherAtom(n)
            if other.GetAtomicNum() == 8 and other.GetIdx() != o_idx:
                return True
    return False


def is_enolic(mol: Chem.Mol, c_idx: int) -> bool:
    """Is the OH-bearing carbon vinylic/enolic (has a double bond to carbon)?"""
    c = mol.GetAtomWithIdx(c_idx)
    for b in c.GetBonds():
        if b.GetBondType() == Chem.BondType.DOUBLE and b.GetOtherAtom(c).GetAtomicNum() == 6:
            return True
    return False


# ---------- Context (allylic/benzylic/propargylic) ----------
def _has_neighboring_cc_double(mol: Chem.Mol, c_idx: int) -> bool:
    """Does this carbon have a carbon neighbor that is in a C=C to another carbon?"""
    c = mol.GetAtomWithIdx(c_idx)
    for n in c.GetNeighbors():
        if n.GetAtomicNum() != 6:
            continue
        for b in n.GetBonds():
            if b.GetBondType() == Chem.BondType.DOUBLE:
                other = b.GetOtherAtom(n)
                if other.GetAtomicNum() == 6:
                    return True
    return False


def _has_neighboring_cc_triple(mol: Chem.Mol, c_idx: int) -> bool:
    """Does this carbon have a carbon neighbor that is in a C≡C to another carbon?"""
    c = mol.GetAtomWithIdx(c_idx)
    for n in c.GetNeighbors():
        if n.GetAtomicNum() != 6:
            continue
        for b in n.GetBonds():
            if b.GetBondType() == Chem.BondType.TRIPLE:
                other = b.GetOtherAtom(n)
                if other.GetAtomicNum() == 6:
                    return True
    return False


def _is_allylic_site(mol: Chem.Mol, c_idx: int) -> bool:
    c = mol.GetAtomWithIdx(c_idx)
    return (
        c.GetHybridization() == Chem.HybridizationType.SP3
        and _has_neighboring_cc_double(mol, c_idx)
        and not c.GetIsAromatic()
    )


def _is_benzylic_site(mol: Chem.Mol, c_idx: int) -> bool:
    """sp3 carbon directly attached to an aromatic carbon (and not on-ring = not phenol)."""
    c = mol.GetAtomWithIdx(c_idx)
    if c.GetHybridization() != Chem.HybridizationType.SP3 or c.GetIsAromatic():
        return False
    return any(nb.GetIsAromatic() and nb.GetAtomicNum() == 6 for nb in c.GetNeighbors())


def _is_propargylic_site(mol: Chem.Mol, c_idx: int) -> bool:
    c = mol.GetAtomWithIdx(c_idx)
    return (
        c.GetHybridization() == Chem.HybridizationType.SP3
        and _has_neighboring_cc_triple(mol, c_idx)
        and not c.GetIsAromatic()
    )


# ---------- Diol motifs (pairwise topology among OH alpha-carbons) ----------
def count_diol_motifs(mol: Chem.Mol, oh_alpha_carbons: list[int]) -> tuple[int, int]:
    """
    Returns (Vicinal12DiolCount, OneThreeDiolCount).

    - 1,2-diol (vicinal): OH alpha carbons directly bonded (graph distance 1).
    - 1,3-diol: OH alpha carbons separated by exactly one **carbon** atom
      (path a–C–b; ignores paths through heteroatoms).
    """
    if len(oh_alpha_carbons) < 2:
        return 0, 0

    # Adjacency for ALL atoms (avoids KeyError for non-OH neighbors)
    num_atoms = mol.GetNumAtoms()
    adj = [set() for _ in range(num_atoms)]
    for i in range(num_atoms):
        adj[i] = {n.GetIdx() for n in mol.GetAtomWithIdx(i).GetNeighbors()}

    vic12 = 0
    one3 = 0

    # Unique unordered pairs (i < j)
    for i, a in enumerate(oh_alpha_carbons):
        for b in oh_alpha_carbons[i + 1:]:
            if b in adj[a]:
                # Directly bonded: vicinal 1,2-diol
                vic12 += 1
            else:
                # Exactly one carbon between a and b: a–C–b
                for m in adj[a]:
                    if mol.GetAtomWithIdx(m).GetAtomicNum() == 6 and b in adj[m]:
                        one3 += 1
                        break

    return vic12, one3


# ---------- Hemiacetal / Hemiketal detection ----------
def _hemiacetal_hemiketal_type(mol: Chem.Mol, c_idx: int, o_idx: int) -> Optional[str]:
    """
    Return "hemiacetal" or "hemiketal" if the OH-bearing center is sp3 and also bound
    to a second single-bond oxygen that is an alkoxy O (OX2H0) connected to carbon.
    Otherwise return None.
    """
    c = mol.GetAtomWithIdx(c_idx)

    # Center must be sp3; enolic/phenolic (sp2) won't qualify by construction.
    if c.GetHybridization() != Chem.HybridizationType.SP3:
        return None

    # Find another O neighbor (besides our OH oxygen) that is single-bonded to c
    other_o = None
    for nb in c.GetNeighbors():
        if nb.GetAtomicNum() != 8 or nb.GetIdx() == o_idx:
            continue
        b = mol.GetBondBetweenAtoms(c_idx, nb.GetIdx())
        if not b or b.GetBondType() != Chem.BondType.SINGLE:
            continue

        # Alkoxy oxygen signature: no hydrogens, and has at least one carbon neighbor
        # other than the central carbon (covers cyclic and acyclic OR).
        if nb.GetTotalNumHs() == 0 and any(
            n2.GetAtomicNum() == 6 and n2.GetIdx() != c_idx for n2 in nb.GetNeighbors()
        ):
            other_o = nb
            break

    if other_o is None:
        return None

    # Safety: exclude any acyl-like C=O on the center (should already be excluded upstream)
    for b in c.GetBonds():
        if b.GetBondType() == Chem.BondType.DOUBLE and b.GetOtherAtom(c).GetAtomicNum() == 8:
            return None

    # Distinguish hemiacetal vs hemiketal by H on the anomeric/central carbon
    return "hemiacetal" if c.GetTotalNumHs() >= 1 else "hemiketal"


# ---------- Main classification and audit ----------
def classify_and_count_alcohols(mol: Chem.Mol):
    """
    Returns:
      p, s, t, phen,
      alpha_hydroxy, enolic,
      allylic, benzylic, propargylic,
      hemiacetal, hemiketal,
      oxime_count,
      oh_alpha_carbons

    Precedence:
      1) Exclude acidic OH
      2) Enolic first (disjoint in strict IUPAC mode; may overlap with P/S/T in descriptor mode)
      3) Alpha-hydroxy (sp3 only; disjoint)
      4) Hemiacetal/hemiketal (context)
      5) Allylic/benzylic/propargylic (context)
      6) Phenol vs P/S/T
    """
    p = s = t = phen = 0
    alpha_hydroxy = 0
    enolic = 0
    allylic = 0
    benzylic = 0
    propargylic = 0
    hemiacetal = 0
    hemiketal = 0

    oxime_count, oxime_o_to_nc = count_oxime_sites(mol)

    oh_alpha_carbons: List[int] = []

    for (o_idx, c_idx) in mol.GetSubstructMatches(OH_PATT, uniquify=True):
        bond = mol.GetBondBetweenAtoms(o_idx, c_idx)
        if not bond or bond.GetBondType() != Chem.BondType.SINGLE:
            continue

        # Exclude imine-bound OH (oximes): [C]=[N]-[OX2H]
        if o_idx in oxime_o_to_nc:
            continue

        attached = mol.GetAtomWithIdx(c_idx)

        # Exclude all S–OH groups
        if attached.GetAtomicNum() == 16:
            continue

        # Exclude all N–OH species that are NOT oximes
        if attached.GetAtomicNum() == 7:
            continue

        # Only carbon-bound OH can be classified into alcohol categories
        if attached.GetAtomicNum() != 6:
            continue

        c = attached

        # Exclude acidic OH (–C(=O)–OH)
        is_acidic_oh = any(
            b.GetBondType() == Chem.BondType.DOUBLE
            and b.GetOtherAtom(c).GetAtomicNum() == 8
            and b.GetOtherAtom(c).GetIdx() != o_idx
            for b in c.GetBonds()
        )
        if is_acidic_oh:
            continue
        # Track alpha-carbon for diol motif analysis
        oh_alpha_carbons.append(c_idx)

        # Flag to prevent double counting (used only when strict mode skips P/S/T classification)
        enol_flag = False

        # 1) Enolic first
        if is_enolic(mol, c_idx):
            enolic += 1
            # Optionally exclude enols entirely from downstream alcohol-type logic
            if EXCLUDE_ENOLS:
                continue
            # Strict IUPAC mode: enols are not classified as alcohols (P/S/T)
            if not COUNT_ENOLS_AS_ALCOHOLS:
                enol_flag = True
                continue
            # Overlap/descriptor mode: fall through and classify degree (P/S/T) by substitution later

        # 2) Context classes (orthogonal tags; should apply even if site is later excluded from P/S/T)
        if _is_allylic_site(mol, c_idx):
            allylic += 1
        if _is_benzylic_site(mol, c_idx):
            benzylic += 1
        if _is_propargylic_site(mol, c_idx):
            propargylic += 1

        # 3) Alpha-hydroxy (sp3-only)
        if (
            is_alpha_to_carbonyl(mol, c_idx, o_idx)
            and c.GetHybridization() == Chem.HybridizationType.SP3
        ):
            alpha_hydroxy += 1
            if EXCLUDE_ALPHA_HYDROXY_CARBONYLS:
                continue
            continue  # Do not double-classify (keep excluded from P/S/T)

        # 4) Hemiacetal / Hemiketal
        hemi = _hemiacetal_hemiketal_type(mol, c_idx, o_idx)
        if hemi == "hemiacetal":
            hemiacetal += 1
        elif hemi == "hemiketal":
            hemiketal += 1

        # 5) Phenol?
        if c.GetIsAromatic():
            phen += 1
            continue

        # 6) Primary / Secondary / Tertiary alcohols
        c_neighbors = sum(
            1 for nb in c.GetNeighbors()
            if nb.GetAtomicNum() == 6 and nb.GetIdx() != o_idx
        )

        # Prevent double-counting if enol already assigned primary
        if not enol_flag:
            if c_neighbors <= 1:
                p += 1
            elif c_neighbors == 2:
                s += 1
            else:
                t += 1

    return (
        p, s, t, phen,
        alpha_hydroxy, enolic,
        allylic, benzylic, propargylic,
        hemiacetal, hemiketal,
        oxime_count,
        oh_alpha_carbons,
    )


def audit_alcohol_sites(mol: Chem.Mol) -> str:
    labels: List[str] = []
    _, oxime_o_to_nc = count_oxime_sites(mol)

    for (o_idx, c_idx) in mol.GetSubstructMatches(OH_PATT, uniquify=True):
        bond = mol.GetBondBetweenAtoms(o_idx, c_idx)
        if not bond or bond.GetBondType() != Chem.BondType.SINGLE:
            continue

        # Oxime OH (imine-bound): [C]=[N]-[OX2H] (excluded from alcohols)
        if o_idx in oxime_o_to_nc:
            if TRACK_EXCLUDED_IN_AUDIT:
                n_idx, c_im_idx = oxime_o_to_nc[o_idx]
                labels.append(f"oxime@O{o_idx}-N{n_idx}-C{c_im_idx}")
            continue

        attached = mol.GetAtomWithIdx(c_idx)

        # Exclude S–OH groups
        if attached.GetAtomicNum() == 16:
            if TRACK_EXCLUDED_IN_AUDIT:
                labels.append(f"sOH_excluded@O{o_idx}-S{c_idx}")
            continue

        # Exclude non-oxime N–OH groups
        if attached.GetAtomicNum() == 7:
            if TRACK_EXCLUDED_IN_AUDIT:
                labels.append(f"nOH_excluded@O{o_idx}-N{c_idx}")
            continue

        # Only carbon-bound OH sites are audited as alcohol categories
        if attached.GetAtomicNum() != 6:
            if TRACK_EXCLUDED_IN_AUDIT:
                labels.append(f"noncarbonOH_excluded@O{o_idx}-A{c_idx}")
            continue

        c = attached

        # Acidic OH? (never an alcohol)
        is_acidic_oh = any(
            b.GetBondType() == Chem.BondType.DOUBLE
            and b.GetOtherAtom(c).GetAtomicNum() == 8
            and b.GetOtherAtom(c).GetIdx() != o_idx
            for b in c.GetBonds()
        )
        if is_acidic_oh:
            if TRACK_EXCLUDED_IN_AUDIT:
                labels.append(f"acidic@O{o_idx}-C{c_idx}")
            continue

        # ENOLIC FIRST — single label
        if is_enolic(mol, c_idx):
            labels.append(f"enol@O{o_idx}-C{c_idx}")
            if EXCLUDE_ENOLS:
                continue
            # Strict IUPAC mode: do not label P/S/T for enols
            if not COUNT_ENOLS_AS_ALCOHOLS:
                continue
        # In overlap/descriptor mode, fall through and also label P/S/T

        # Hemiacetal / Hemiketal audit tag
        hemi = _hemiacetal_hemiketal_type(mol, c_idx, o_idx)
        if hemi == "hemiacetal":
            labels.append(f"hemiacetal@O{o_idx}-C{c_idx}")
        elif hemi == "hemiketal":
            labels.append(f"hemiketal@O{o_idx}-C{c_idx}")

        # Alpha-hydroxy (sp3 only)
        if (
            is_alpha_to_carbonyl(mol, c_idx, o_idx)
            and c.GetHybridization() == Chem.HybridizationType.SP3
        ):
            if TRACK_EXCLUDED_IN_AUDIT:
                labels.append(f"alpha2carbonyl@O{o_idx}-C{c_idx}")
            if EXCLUDE_ALPHA_HYDROXY_CARBONYLS:
                continue
            continue

        # Phenol?
        if c.GetIsAromatic():
            labels.append(f"phenol@O{o_idx}-C{c_idx}")
            continue

        # P/S/T
        cdeg = sum(
            1 for nb in c.GetNeighbors() if nb.GetAtomicNum() == 6 and nb.GetIdx() != o_idx
        )
        tag = "primary" if cdeg <= 1 else "secondary" if cdeg == 2 else "tertiary"
        labels.append(f"{tag}@O{o_idx}-C{c_idx}")

    return "; ".join(labels) if labels else ""