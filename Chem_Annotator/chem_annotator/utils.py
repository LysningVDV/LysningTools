import re
from html import unescape
from typing import List
import pandas as pd
from rdkit import Chem
from rdkit.Chem.rdmolops import GetSymmSSSR

# ----------- generic helpers -----------
def count_smarts(mol: Chem.Mol, patt: Chem.Mol) -> int:
    if patt is None:
        return 0
    return len(mol.GetSubstructMatches(patt, uniquify=True))

def get_ring_sets(mol: Chem.Mol) -> List[set]:
    """Return rings as list of sets of atom indices."""
    return [set(r) for r in GetSymmSSSR(mol)]

def atoms_in_same_ring(ringsets: List[set], *atom_indices: int) -> bool:
    """True if all atom_indices are contained within any single ring set."""
    atoms = set(atom_indices)
    return any(atoms.issubset(r) for r in ringsets)

def count_unsaturated_bonds(mol: Chem.Mol) -> int:
    n = 0
    for b in mol.GetBonds():
        if b.GetIsAromatic():
            n += 1
        elif b.GetBondType() in (Chem.BondType.DOUBLE, Chem.BondType.TRIPLE):
            n += 1
    return n

# ----------- SMILES cleaning -----------
NBSP = "\xa0"  # Unicode NBSP
_ctrl_re = re.compile(r"[\x00-\x1F]")  # control chars

def clean_smiles(x) -> str:
    """
    Normalize SMILES-like strings that may contain HTML entities, NBSP, or multiple fragments.

    This function implements the project-wide canonical **dot-SMILES policy**, ensuring that
    multi-fragment SMILES resolve to a single, deterministic "main" fragment before feature
    extraction.

    Normalization steps:
      1) Convert None/NaN → ''.
      2) Apply html.unescape to resolve entities such as '&nbsp;' or '&lt;'.
      3) Replace Unicode NBSP with a standard space and strip whitespace.
      4) Remove ASCII control characters.
      5) If the result is empty or equals 'nbsp' (common artifact), return ''.

    Dot‑SMILES ('.') resolution policy — canonical rules:
      • Split into fragments on '.' and discard empty pieces.
      • For each fragment f:
          - Attempt RDKit parsing.
          - If parsing succeeds:
                * Compute `heavy = number of heavy atoms`.
                * Compute `has_c = whether fragment contains at least one carbon atom`.
                * Score fragment as (has_c_flag, heavy_atom_count, fragment_string).
      • Selection:
          - Prefer carbon-containing fragments over carbon-free fragments.
          - Among fragments tied on carbon presence, choose the one with the highest
            heavy-atom count.
          - If at least one fragment parsed successfully, select the highest-scoring one.
          - If none of the fragments parse, fall back to the longest fragment by string length.

    Returns:
        A cleaned, single-fragment SMILES string suitable for RDKit parsing and downstream
        feature extraction. Returns '' if cleaning or resolution fails.

    Notes:
        - This policy ensures reproducible selection across all modules.
        - The scoring tuple ordering implicitly enforces the carbon-first preference,
          followed by molecular size, with deterministic tie-breaking via Python sorting.
    """
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return ""
    s = str(x)
    s = unescape(s)              # decode HTML entities
    s = s.replace(NBSP, " ").strip()
    if not s:
        return ""
    s = _ctrl_re.sub("", s).strip()
    if not s or s.lower() == "nbsp":
        return ""

    # --- Option 1: Keep largest organic fragment if multi-fragment SMILES ---
    if "." in s:
        frags = [f.strip() for f in s.split(".") if f.strip()]
        if not frags:
            return ""

        scored = []
        for f in frags:
            m = Chem.MolFromSmiles(f)
            if m is None:
                continue
            heavy = m.GetNumHeavyAtoms()
            has_c = any(a.GetAtomicNum() == 6 for a in m.GetAtoms())
            # Score: prefer carbon-containing fragments first, then heavy atom count
            scored.append((1 if has_c else 0, heavy, f))

        if scored:
            scored.sort(reverse=True)  # (has_c, heavy, frag) descending
            return scored[0][2]

        # Fallback heuristic: keep the longest fragment (often the main organic component)
        return max(frags, key=len)

    return s