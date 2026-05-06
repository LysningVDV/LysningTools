import logging
import time
import requests
from datetime import datetime

logger = logging.getLogger(__name__)

OPSIN_BASE = "https://opsin.ch.cam.ac.uk/opsin"
TIMEOUT = 8
RETRIES = 3
RETRY_DELAY = 1.5


def resolve_opsin_cas(identifier: str) -> dict | None:
    """
    Resolve an input identifier (CAS or name) using OPSIN.

    OPSIN is mainly intended for organic chemical NAMES.
    It typically does not resolve CAS numbers, but can sometimes
    interpret identifiers that are name-like.

    Returns
    -------
    dict | None
        {
            "smiles": "...",
            "inchi": "...",
            "inchikey": "...",
            "mw": None,
            "warning_list": [...],
            "timestamp": "...Z"
        }
        or None if not resolved.
    """
    warnings = []

    try:
        data = _query_opsin(identifier, warnings)
        if not data:
            warnings.append("OPSIN: no result")
            return None

        return {
            "smiles": data.get("smiles", ""),
            "inchi": data.get("inchi", ""),
            "inchikey": data.get("inchikey", ""),
            "mw": None,  # RDKit will derive later
            "warning_list": warnings[:],
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

    except Exception as exc:
        logger.debug("OPSIN lookup crashed for '%s': %s", identifier, exc)
        warnings.append(f"OPSIN crash: {exc}")
        return None


# --------------------------------------------------------------------
# INTERNAL FUNCTIONS
# --------------------------------------------------------------------

def _query_opsin(identifier: str, warnings: list) -> dict | None:
    """
    Query OPSIN /<name>.json endpoint.

    OPSIN returns JSON containing:
        {"status": "OK", "smiles": "...", "inchi": "...", ...}

    Parameters
    ----------
    identifier : str
    warnings : list

    Returns
    -------
    dict | None
    """
    # OPSIN requires URL-encoded inputs handled by requests automatically
    url = f"{OPSIN_BASE}/{identifier}.json"

    for attempt in range(RETRIES):
        try:
            logger.debug("OPSIN fetch attempt %d for '%s'", attempt + 1, identifier)
            r = requests.get(url, timeout=TIMEOUT, headers={"Accept": "application/json"})

            if r.status_code == 200:
                try:
                    data = r.json()
                except ValueError:
                    warnings.append("OPSIN: invalid JSON response")
                    return None

                if data.get("status") != "OK":
                    warnings.append(f"OPSIN: status={data.get('status')}")
                    return None

                return {
                    "smiles": data.get("smiles", ""),
                    "inchi": data.get("inchi", ""),
                    "inchikey": data.get("inchikey", "")
                }

            elif r.status_code == 404:
                return None

            else:
                warnings.append(f"OPSIN HTTP {r.status_code}")

        except requests.exceptions.Timeout:
            warnings.append("OPSIN timeout")
        except Exception as exc:
            warnings.append(f"OPSIN error: {exc}")

        time.sleep(RETRY_DELAY)

    return None