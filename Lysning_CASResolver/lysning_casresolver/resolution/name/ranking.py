import logging
import unicodedata

logger = logging.getLogger(__name__)


def rank_candidates(original_name: str,
                    normalized_name: str,
                    candidates: list[dict]):
    """
    Rank PubChem CID candidates for a given chemical name.

    Ranking rules (priority order, additive scoring):
      1. Exact synonym match (very strong)
      2. Cleaned synonym match (lowercase + accent-stripped)
      3. Organic preference (SMILES contains carbon backbone)
      4. Non-salt preference (no '.' in SMILES)
      5. Charge penalty (fewer +/- characters in InChIKey)
      6. Heavy atom count distance from median (smaller is better)
      7. Lower CID as final tie-breaker

    Parameters
    ----------
    original_name : str
        The user-provided input before normalization.
    normalized_name : str
        The output from normalize_name().
    candidates : list of dict
        Each dict must contain:
            {
                "cid": str,
                "smiles": str,
                "inchi": str,
                "inchikey": str,
                "mw": float,
                "synonyms": [str, ...]
            }

    Returns
    -------
    best_candidate : dict
    ranking_details : list of dict
        Each detail entry includes:
            {
                "cid": ...,
                "score": ...,
                "rules": [...]
            }
    """
    if not candidates:
        return None, []

    # Pre-clean names
    orig_clean = _strip_accents(original_name.lower().strip())
    norm_clean = _strip_accents(normalized_name.lower().strip())

    # Precompute atom median for penalty scoring
    median_atoms = _median_heavy_atoms(candidates)

    scored = []

    for cand in candidates:
        cid = cand["cid"]
        smiles = cand.get("smiles", "")
        synonyms = [s.lower() for s in cand.get("synonyms", [])]
        synonyms_clean = [_strip_accents(s.lower()) for s in synonyms]

        score = 0
        detail = {"cid": cid, "score": 0, "rules": []}

        # Rule 1 — Exact synonym match
        if normalized_name in synonyms or normalized_name in synonyms_clean:
            score += 1000
            detail["rules"].append("exact_synonym_match")

        # Rule 2 — Cleaned synonym match (lowercase + accent stripping)
        if norm_clean in synonyms_clean or orig_clean in synonyms_clean:
            score += 500
            detail["rules"].append("cleaned_synonym_match")

        # Rule 3 — Organic preference: look for carbon atoms
        if "c" in smiles.lower():
            score += 50
            detail["rules"].append("organic_preference")

        # Rule 4 — Non-salt preference: salt SMILES often include "."
        if "." not in smiles:
            score += 25
            detail["rules"].append("non_salt_preference")

        # Rule 5 — Charge penalty: InChIKey contains '+' or '-'
        inchikey = cand.get("inchikey", "")
        charge = inchikey.count("+") + inchikey.count("-")
        if charge > 0:
            detail["rules"].append("charge_penalty")
        score -= charge

        # Rule 6 — Heavy atom count closeness to median
        heavy_atoms = _estimate_heavy_atoms(smiles)
        if heavy_atoms is not None:
            penalty = abs(heavy_atoms - median_atoms)
            score -= penalty
            detail["rules"].append("heavy_atom_similarity_penalty")

        # Rule 7 — Lower CID ties break last
        try:
            cid_value = int(cid)
            score += (1 / (1 + cid_value))
        except Exception:
            pass  # Non-numeric CIDs not expected, but no penalty

        detail["score"] = score
        scored.append(detail)

    # Sort by descending score
    sorted_details = sorted(scored, key=lambda x: x["score"], reverse=True)

    # Top candidate = best match
    best_cid = sorted_details[0]["cid"]
    best = next(c for c in candidates if c["cid"] == best_cid)

    return best, sorted_details


# ---------------------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------------------

def _strip_accents(s: str) -> str:
    """Remove accents using NFD decomposition."""
    nfkd = unicodedata.normalize("NFD", s)
    return nfkd.encode("ascii", "ignore").decode("ascii")


def _estimate_heavy_atoms(smiles: str) -> int:
    """
    Simple heuristic: count uppercase alphabetical characters as heavy atoms.

    This is NOT chemically exact, but effective for ranking heuristics.
    """
    if not smiles:
        return None
    return sum(1 for c in smiles if c.isalpha() and c.isupper())


def _median_heavy_atoms(candidates: list[dict]) -> int:
    """
    Compute the median heavy atom count across candidate SMILES.
    """
    counts = []
    for c in candidates:
        smiles = c.get("smiles", "")
        if smiles:
            n = _estimate_heavy_atoms(smiles)
            if n is not None:
                counts.append(n)

    if not counts:
        return 0

    counts.sort()
    mid = len(counts) // 2
    return counts[mid]