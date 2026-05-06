import logging
from datetime import datetime

from .normalize import normalize_name
from .cid_lookup import fetch_cids_for_name, fetch_properties_for_cid
from .ranking import rank_candidates

logger = logging.getLogger(__name__)


def resolve_name(name: str) -> dict | None:
    """
    High-level name resolver for chemical names using PubChem.

    Steps:
      1. Normalize name
      2. Query PubChem for list of matching CIDs
      3. Fetch structure properties and synonyms for each CID
      4. Rank all candidate structures
      5. Return:
            {
                "best": {...structure dict...},
                "candidates": [...],
                "ranking_details": [...],
                "warning_list": [...],
                "timestamp": "...Z"
            }

    If no resolution is possible, returns None.
    """
    warnings = []

    # --------------------------------------------------------------
    # 1. Normalize
    # --------------------------------------------------------------
    normalized, w = normalize_name(name)
    if w:
        warnings.append(w)

    if not normalized:
        warnings.append("empty or invalid name input")
        return None

    # --------------------------------------------------------------
    # 2. Fetch CIDs
    # --------------------------------------------------------------
    cids = fetch_cids_for_name(normalized, warnings)
    if not cids:
        warnings.append("no CIDs found for name")
        return None

    # --------------------------------------------------------------
    # 3. Fetch properties for each CID
    # --------------------------------------------------------------
    candidates = []
    for cid in cids:
        props = fetch_properties_for_cid(cid, warnings)
        if props:
            candidates.append(props)

    if not candidates:
        warnings.append("CIDs found but no candidate properties resolved")
        return None

    # --------------------------------------------------------------
    # 4. Rank candidates
    # --------------------------------------------------------------
    best, ranking_details = rank_candidates(name, normalized, candidates)

    # --------------------------------------------------------------
    # 5. Build final structured result
    # --------------------------------------------------------------
    timestamp = datetime.utcnow().isoformat() + "Z"

    result = {
        "best": best,
        "candidates": candidates,
        "ranking_details": ranking_details,
        "warning_list": warnings[:],
        "timestamp": timestamp
    }

    logger.debug("Name resolution for '%s' → best CID %s",
                 name, best.get("cid"))

    return result