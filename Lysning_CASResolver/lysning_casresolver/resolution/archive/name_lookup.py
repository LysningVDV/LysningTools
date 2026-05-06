import logging
import time
import requests
import unicodedata
from datetime import datetime

logger = logging.getLogger(__name__)

PUBCHEM_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
TIMEOUT = 10
RETRIES = 3
RETRY_DELAY = 1.5


# ---------------------------------------------------------------------
# PUBLIC ENTRY POINT
# ---------------------------------------------------------------------

def resolve_name(name: str) -> dict | None:
    """
    Resolve a chemical name via PubChem PUG-REST with enhanced:
      - name normalization (accent removal, lowercasing, whitespace cleanup)
      - CID search with multiple candidates
      - Ranked CID selection
      - Structured result: best + candidates + ranking details

    Returns
    -------
    dict | None:
        {
           "best": {...},
           "candidates": [...],
           "ranking_details": [...],
           "warning_list": [...],
           "timestamp": "...Z"
        }
        or None if no result.
    """
    warnings = []

    # 1. Normalize name
    normalized, norm_warning = _normalize_name(name)
    if norm_warning:
        warnings.append(norm_warning)

    # 2. Query PubChem for CIDs
    cids = _name_to_cids(normalized, warnings)
    if not cids:
        warnings.append("PubChem: no CIDs found for name")
        return None

    # 3. Fetch property blocks for all CIDs
    candidates = []
    for cid in cids:
        props = _cid_to_properties(cid, warnings)
        if props:
            props["cid"] = cid
            candidates.append(props)

    if not candidates:
        warnings.append("PubChem: CIDs returned, but no properties resolved")
        return None

    # 4. Rank candidates
    best, ranking_details = _rank_candidates(name, normalized, candidates)

    return {
        "best": best,
        "candidates": candidates,
        "ranking_details": ranking_details,
        "warning_list": warnings[:],
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
# ---------------------------------------------------------------------
# INTERNAL: NAME NORMALIZATION
# ---------------------------------------------------------------------

def _normalize_name(name: str) -> tuple[str, str]:
    """
    Normalize a chemical name with:
      - strip and collapse whitespace
      - lowercase
      - accent stripping (ASCII fold)
      - punctuation trimming

    Returns
    -------
    normalized_name : str
    warning : str
    """
    original = name

    # Basic cleanup
    name = name.strip()
    name = " ".join(name.split())
    name = name.lower()

    # Strip accents — NFD decomposition + ASCII encode
    nfkd = unicodedata.normalize("NFD", name)
    name = nfkd.encode("ascii", "ignore").decode("ascii")

    # Remove trailing commas, semicolons, periods
    while name and name[-1] in ",.;:":
        name = name[:-1]

    warning = ""
    if name != original:
        warning = "name normalization applied"

    return name, warning


# ---------------------------------------------------------------------
# INTERNAL: NAME → CID LIST
# ---------------------------------------------------------------------

def _name_to_cids(normalized_name: str, warnings: list) -> list[str]:
    """
    Query PubChem name→CID, but allow multiple CIDs.
    """
    url = f"{PUBCHEM_BASE}/compound/name/{normalized_name}/cids/JSON"

    for attempt in range(RETRIES):
        try:
            logger.debug("PubChem name→CID attempt %d for '%s'",
                         attempt + 1, normalized_name)

            r = requests.get(url, timeout=TIMEOUT)
            if r.status_code == 200:
                data = r.json()
                cids = data.get("IdentifierList", {}).get("CID", [])
                return [str(cid) for cid in cids]
            elif r.status_code == 404:
                return []
            else:
                warnings.append(f"name→CID HTTP {r.status_code}")

        except requests.exceptions.Timeout:
            warnings.append("name→CID timeout")
        except Exception as exc:
            warnings.append(f"name→CID error: {exc}")

        time.sleep(RETRY_DELAY)

    return []


# ---------------------------------------------------------------------
# INTERNAL: CID → STRUCTURE PROPERTIES
# ---------------------------------------------------------------------

def _cid_to_properties(cid: str, warnings: list) -> dict | None:
    """
    Retrieve structural properties for a CID:
      - SMILES
      - InChI
      - InChIKey
      - MW
      - Synonyms (for ranking)

    Returns dict or None.
    """
    # Include synonyms in the request
    url = (
        f"{PUBCHEM_BASE}/compound/cid/{cid}/property/"
        "IsomericSMILES,InChI,InChIKey,MolecularWeight/JSON"
    )
    syn_url = f"{PUBCHEM_BASE}/compound/cid/{cid}/synonyms/JSON"

    smiles = inchi = inchikey = None
    mw = None
    synonyms = []

    # 1. Main property fetch
    for attempt in range(RETRIES):
        try:
            r = requests.get(url, timeout=TIMEOUT)
            if r.status_code == 200:
                props = r.json().get("PropertyTable", {}).get("Properties", [])
                if props:
                    p = props[0]
                    smiles = p.get("IsomericSMILES", "")
                    inchi = p.get("InChI", "")
                    inchikey = p.get("InChIKey", "")
                    try:
                        mw = float(p.get("MolecularWeight"))
                    except Exception:
                        mw = None
                break
            elif r.status_code == 404:
                return None
            else:
                warnings.append(f"CID property HTTP {r.status_code}")
        except Exception as exc:
            warnings.append(f"CID property error: {exc}")
        time.sleep(RETRY_DELAY)

    # 2. Synonyms fetch
    for attempt in range(RETRIES):
        try:
            r = requests.get(syn_url, timeout=TIMEOUT)
            if r.status_code == 200:
                syns = r.json().get("InformationList", {}).get("Information", [])
                if syns:
                    synonyms = syns[0].get("Synonym", [])
                break
            elif r.status_code == 404:
                synonyms = []
                break
            else:
                warnings.append(f"CID synonym HTTP {r.status_code}")
        except Exception as exc:
            warnings.append(f"CID synonym error: {exc}")
        time.sleep(RETRY_DELAY)

    if not smiles and not inchi:
        return None

    return {
        "cid": cid,
        "smiles": smiles or "",
        "inchi": inchi or "",
        "inchikey": inchikey or "",
        "mw": mw,
        "synonyms": synonyms
    }


# ---------------------------------------------------------------------
# INTERNAL: CANDIDATE RANKING ENGINE
# ---------------------------------------------------------------------

def _rank_candidates(original_name: str,
                     normalized_name: str,
                     candidates: list[dict]):
    """
    Rank multiple CID candidates using:
      1. Exact synonym match
      2. Accent- and case-insensitive match
      3. Prefer organics
      4. Prefer non-salts
      5. Lowest charge magnitude
      6. Heavy atom count similarity
      7. Lowest CID number as tie-breaker

    Returns (best_candidate_dict, ranking_details).
    """
    ranking_details = []

    # Preprocess search strings
    orig_clean = _strip_accents(original_name.lower().strip())
    norm_clean = _strip_accents(normalized_name.lower().strip())

    # Prepare scores for each candidate
    scored = []

    for cand in candidates:
        cid = cand["cid"]
        synonyms = [s.lower() for s in cand.get("synonyms", [])]

        syn_clean = [_strip_accents(s) for s in synonyms]

        score = 0
        detail = {"cid": cid, "score": 0, "rules": []}

        # Rule 1: Exact synonym match (highest)
        if normalized_name in synonyms or normalized_name in syn_clean:
            score += 1000
            detail["rules"].append("exact_synonym_match")

        # Rule 2: Loose cleaned match (case + accent-insensitive)
        if norm_clean in syn_clean:
            score += 500
            detail["rules"].append("cleaned_synonym_match")

        # Rule 3: Prefer organics (simple heuristic: at least 1 C atom)
        heavy_atoms = _estimate_heavy_atoms(cand.get("smiles", ""))
        if heavy_atoms and "c" in cand.get("smiles", "").lower():
            score += 50
            detail["rules"].append("organic_preference")

        # Rule 4: Prefer non-salt (heuristic: no '.' in SMILES)
        if "." not in cand.get("smiles", ""):
            score += 25
            detail["rules"].append("non_salt_preference")

        # Rule 5: Charge minimization via "+" or "-"
        charge = cand.get("inchikey", "").count("+") + cand.get("inchikey", "").count("-")
        score -= charge
        if charge:
            detail["rules"].append("charge_penalty")

        # Rule 6: Heavy atom count closeness to median
        # (used only to improve ranking within similar candidates)
        score -= abs((heavy_atoms or 0) - _median_heavy_atoms(candidates))
        detail["rules"].append("heavy_atom_similarity_penalty")

        # Rule 7: Lowest CID wins ties
        score += (1 / (1 + int(cid)))

        detail["score"] = score
        scored.append(detail)

    # Sort by score descending
    scored_sorted = sorted(scored, key=lambda x: x["score"], reverse=True)

    # Best candidate = the top-ranked one
    best_cid = scored_sorted[0]["cid"]
    best = next(c for c in candidates if c["cid"] == best_cid)

    ranking_details.extend(scored_sorted)
    return best, ranking_details


# ---------------------------------------------------------------------
# INTERNAL HELPERS
# ---------------------------------------------------------------------

def _strip_accents(s: str) -> str:
    nfkd = unicodedata.normalize("NFD", s)
    return nfkd.encode("ascii", "ignore").decode("ascii")


def _estimate_heavy_atoms(smiles: str) -> int:
    """Rough heuristic: count uppercase letters as heavy atoms."""
    return sum(1 for c in smiles if c.isalpha() and c.isupper())


def _median_heavy_atoms(candidates: list[dict]) -> int:
    vals = []
    for c in candidates:
        smiles = c.get("smiles", "")
        if smiles:
            vals.append(_estimate_heavy_atoms(smiles))
    if not vals:
        return 0
    vals.sort()
    mid = len(vals) // 2
    return vals[mid]