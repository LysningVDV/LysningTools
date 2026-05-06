# chem_annotator/aldehydes.py
from typing import List, Tuple, Dict
from rdkit import Chem

def _is_aldehyde_center(mol: Chem.Mol, c_idx: int) -> Tuple[bool, int, int]:
    """
    Return (is_aldehyde, o_idx, alpha_idx) for a candidate carbonyl carbon.
    Criteria:
      - carbonyl C has a double bond to O,
      - carbonyl C has >=1 H (aldehydic),
      - there is a single-bonded carbon neighbor (alpha carbon).
    """
    c = mol.GetAtomWithIdx(c_idx)
    if c.GetAtomicNum() != 6:
        return False, -1, -1

    # C=O
    o_idx = -1
    for b in c.GetBonds():
        if b.GetBondType() == Chem.BondType.DOUBLE:
            other = b.GetOtherAtom(c)
            if other.GetAtomicNum() == 8:
                o_idx = other.GetIdx()
                break
    if o_idx < 0:
        return False, -1, -1

    # aldehydic hydrogen
    if c.GetTotalNumHs() < 1:
        return False, -1, -1

    # alpha carbon (single-bonded carbon neighbor)
    alpha_idx = -1
    for nb in c.GetNeighbors():
        if nb.GetAtomicNum() == 6:
            b = mol.GetBondBetweenAtoms(c_idx, nb.GetIdx())
            if b and b.GetBondType() == Chem.BondType.SINGLE:
                alpha_idx = nb.GetIdx()
                break
    if alpha_idx < 0:
        return False, -1, -1

    return True, o_idx, alpha_idx


def find_aldehyde_centers(mol: Chem.Mol) -> List[Tuple[int, int, int]]:
    """Return list of (c_idx, o_idx, alpha_idx) for all aldehyde centers."""
    centers: List[Tuple[int, int, int]] = []
    for c in mol.GetAtoms():
        ok, o_idx, alpha_idx = _is_aldehyde_center(mol, c.GetIdx())
        if ok:
            centers.append((c.GetIdx(), o_idx, alpha_idx))
    return centers


def _is_aromatic_alpha(mol: Chem.Mol, alpha_idx: int) -> bool:
    return mol.GetAtomWithIdx(alpha_idx).GetIsAromatic()


def _is_alpha_in_ring(mol: Chem.Mol, alpha_idx: int) -> bool:
    return mol.GetAtomWithIdx(alpha_idx).IsInRing()


def _is_alpha_substituted(mol: Chem.Mol, c_idx: int, alpha_idx: int) -> bool:
    """
    Carbon-only steric proxy:
    Alpha substituted if alpha carbon has >=2 SINGLE-bond carbon neighbors besides the aldehyde carbonyl carbon.
    (i.e., true alkyl branching at alpha; hetero substituents like OH/halogens do not trigger this bucket.)
    """
    alpha = mol.GetAtomWithIdx(alpha_idx)

    carbon_subs = 0
    for bond in alpha.GetBonds():
        nbr = bond.GetOtherAtom(alpha)
        if nbr.GetIdx() == c_idx:
            continue
        if bond.GetBondType() != Chem.BondType.SINGLE:
            continue
        if nbr.GetAtomicNum() == 6:
            carbon_subs += 1

    return carbon_subs >= 2


def _is_beta_substituted_aliphatic(mol: Chem.Mol, c_idx: int, alpha_idx: int) -> bool:
    """
    Carbon-only steric proxy:
    For aliphatic side chains (alpha not in ring), beta substituted if any beta carbon
    (neighbor of alpha excluding the aldehyde carbonyl carbon) is carbon-branched,
    meaning it has >= 2 SINGLE-bond carbon neighbors besides alpha.

    Exclusions:
      - Carbonyl carbons (C=O) are not treated as beta carbons to avoid misclassifying
        aldehydes adjacent to ketones/esters/acids as beta-substituted.
      - Hetero substituents (e.g., OH, halogens) do NOT trigger beta-substitution in this model.
    """
    alpha = mol.GetAtomWithIdx(alpha_idx)

    def _is_carbonyl_carbon(a: Chem.Atom) -> bool:
        if a.GetAtomicNum() != 6:
            return False
        return any(
            (b.GetBondType() == Chem.BondType.DOUBLE and b.GetOtherAtom(a).GetAtomicNum() == 8)
            for b in a.GetBonds()
        )

    # Candidate beta carbons: carbon neighbors of alpha excluding the aldehyde carbonyl carbon,
    # excluding carbonyl carbons entirely.
    betas = [
        n for n in alpha.GetNeighbors()
        if n.GetIdx() != c_idx and n.GetAtomicNum() == 6 and not _is_carbonyl_carbon(n)
    ]
    if not betas:
        return False

    for b in betas:
        carbon_subs = 0
        for bond in b.GetBonds():
            nbr = bond.GetOtherAtom(b)
            if nbr.GetIdx() == alpha_idx:
                continue
            if bond.GetBondType() != Chem.BondType.SINGLE:
                continue
            if nbr.GetAtomicNum() == 6:
                carbon_subs += 1

        # beta carbon branching: at least two carbon substituents besides alpha
        if carbon_subs >= 2:
            return True

    return False



def _cyclic_beta_sub_count(mol: Chem.Mol, alpha_idx: int) -> int:
    """
    When alpha is in a ring (aryl or aliphatic), 'beta' positions are the ring neighbors of alpha
    (the two ring atoms adjacent to alpha along the ring path).
    Return how many of those beta ring atoms are 'substituted', defined as degree > 2
    (i.e., any extra substituent beyond the two ring bonds and the alpha link).
    We cap the count at 2.
    """
    alpha = mol.GetAtomWithIdx(alpha_idx)
    beta_ring_atoms = [n for n in alpha.GetNeighbors() if n.IsInRing()]  # typically 2
    sub = 0
    for b in beta_ring_atoms:
        if b.GetDegree() > 2:
            sub += 1
    return min(sub, 2)


def _is_alpha_beta_unsaturated(mol: Chem.Mol, alpha_idx: int) -> bool:
    """
    'ab-unsat' if:
      - alpha carbon has a C=C to a carbon (enal), OR
      - alpha carbon is aromatic (conjugated directly into an aromatic ring).
    """
    a = mol.GetAtomWithIdx(alpha_idx)
    if a.GetIsAromatic():
        return True
    for b in a.GetBonds():
        if b.GetBondType() == Chem.BondType.DOUBLE and b.GetOtherAtom(a).GetAtomicNum() == 6:
            return True
    return False


def classify_aldehyde(mol: Chem.Mol) -> Tuple[Dict[str, int], str]:
    """
    Classify all aldehyde centers and return:
      counts: dict of counters
      audit:  semicolon-separated summary per center
    """
    centers = find_aldehyde_centers(mol)
    counts = {
        "AldehydeCount": 0,

        # Acyclic steric substitution classes (mutually exclusive):
        # alpha-sub = carbon branching at alpha
        # beta-sub  = carbon branching at beta
        # neither   = no carbon branching at alpha or beta
        "AldehydeCount_AlphaSubstituted": 0,
        "AldehydeCount_BetaSubstituted": 0,
        "AldehydeCount_NoAlphaBetaSub": 0,

        # Context: aryl vs cyclic aliphatic
        "ArylAldehydeCount": 0,
        "CyclicAliphaticAldehydeCount": 0,

        # Cyclic β-sub granularity
        "CyclicAldehyde_BetaSubCount_0": 0,
        "CyclicAldehyde_BetaSubCount_1": 0,
        "CyclicAldehyde_BetaSubCount_2": 0,

        # Back-compat rollups (computed at end)
        "CyclicAldehyde_BetaSubstitutedCount": 0,
        "CyclicAldehyde_NonBetaSubstitutedCount": 0,

        # α,β-unsaturation
        "AlphaBetaUnsaturatedAldehydeCount": 0,
    }

    labels: List[str] = []
    counts["AldehydeCount"] = len(centers)

    for c_idx, o_idx, alpha_idx in centers:
        alpha_arom = _is_aromatic_alpha(mol, alpha_idx)
        alpha_ring = _is_alpha_in_ring(mol, alpha_idx)
        ab_unsat = _is_alpha_beta_unsaturated(mol, alpha_idx)

        # Context flags
        if alpha_arom:
            counts["ArylAldehydeCount"] += 1
        elif alpha_ring:
            counts["CyclicAliphaticAldehydeCount"] += 1

        # Cyclic β substitution detail (only when alpha is in a ring)
        # Cyclic β substitution detail (only when alpha is in a NON-aromatic ring)
        # Aryl aldehydes have their own context counter (ArylAldehydeCount) and should not populate
        # CyclicAldehyde_BetaSubCount_* buckets.
        cyclic_beta = None
        if alpha_ring and not alpha_arom:
            n_sub = _cyclic_beta_sub_count(mol, alpha_idx)
            if n_sub == 0:
                counts["CyclicAldehyde_BetaSubCount_0"] += 1
            elif n_sub == 1:
                counts["CyclicAldehyde_BetaSubCount_1"] += 1
            else:
                counts["CyclicAldehyde_BetaSubCount_2"] += 1
            cyclic_beta = f"cyclicBetaSub={n_sub}"
        # Aliphatic side-chain substitution classes (mutually exclusive) when not in ring
        ab_tag = None
        if not alpha_ring:
            if _is_alpha_substituted(mol, c_idx, alpha_idx):
                counts["AldehydeCount_AlphaSubstituted"] += 1
                ab_tag = "alphaSub"
            elif _is_beta_substituted_aliphatic(mol, c_idx, alpha_idx):
                counts["AldehydeCount_BetaSubstituted"] += 1
                ab_tag = "betaSub"
            else:
                counts["AldehydeCount_NoAlphaBetaSub"] += 1
                ab_tag = "noAlphaBetaSub"

        # α,β-unsaturation (enal or aryl-conjugated)
        if ab_unsat:
            counts["AlphaBetaUnsaturatedAldehydeCount"] += 1

        # Build per-center audit
        tags = [f"ald@C{c_idx}"]
        if ab_tag:
            tags.append(ab_tag)
        if cyclic_beta:
            tags.append(cyclic_beta)
        if alpha_arom:
            tags.append("aryl")
        elif alpha_ring:
            tags.append("cyclic-aliph")
        else:
            tags.append("acyclic")
        if ab_unsat:
            tags.append("ab-unsat")
        labels.append(":".join(tags))

    # Back-compat rollups
    counts["CyclicAldehyde_BetaSubstitutedCount"] = (
        counts["CyclicAldehyde_BetaSubCount_1"] + counts["CyclicAldehyde_BetaSubCount_2"]
    )
    counts["CyclicAldehyde_NonBetaSubstitutedCount"] = counts["CyclicAldehyde_BetaSubCount_0"]

    return counts, "; ".join(labels)