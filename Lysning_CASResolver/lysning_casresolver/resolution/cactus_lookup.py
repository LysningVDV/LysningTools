import logging
import time
import requests
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://cactus.nci.nih.gov/chemical/structure"
TIMEOUT = 8
RETRIES = 3
RETRY_DELAY = 1.5


def resolve_cactus_cas(cas: str) -> dict | None:
    """
    Resolve a CAS number into SMILES / InChI / InChIKey using the
    NCI Cactus Chemical Identifier Resolver.

    Cactus supports:
        /<identifier>/smiles
        /<identifier>/stdinchi
        /<identifier>/stdinchikey

    The service is not 100% reliable, so retry and fallback logic is required.

    Parameters
    ----------
    cas : str

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
        smiles = _query_cactus(cas, "smiles", warnings)
        inchi = _query_cactus(cas, "stdinchi", warnings)
        inchikey = _query_cactus(cas, "stdinchikey", warnings)

        if not smiles and not inchi:
            warnings.append("Cactus: no structure returned")
            return None

        return {
            "smiles": smiles or "",
            "inchi": inchi or "",
            "inchikey": inchikey or "",
            "mw": None,  # RDKit will calculate later
            "warning_list": warnings[:],
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

    except Exception as exc:
        logger.debug("Cactus lookup crashed for CAS %s: %s", cas, exc)
        warnings.append(f"Cactus crash: {exc}")
        return None


# --------------------------------------------------------------------
# INTERNAL FUNCTIONS
# --------------------------------------------------------------------

def _query_cactus(identifier: str, rep: str, warnings: list) -> str | None:
    """
    Query Cactus for a specific representation.

    Examples:
      /<identifier>/smiles
      /<identifier>/stdinchi
      /<identifier>/stdinchikey

    Parameters
    ----------
    identifier : str
    rep : str
    warnings : list

    Returns
    -------
    str | None
    """
    url = f"{BASE_URL}/{identifier}/{rep}"

    for attempt in range(RETRIES):
        try:
            logger.debug("Cactus fetch %s attempt %d for %s", rep, attempt + 1, identifier)
            r = requests.get(url, timeout=TIMEOUT)
            if r.status_code == 200:
                text = r.text.strip()
                # Cactus may respond with "Not Found" as plain text
                if text.lower() in ("not found", "notfound"):
                    return None
                return text

            elif r.status_code == 404:
                return None
            else:
                warnings.append(f"Cactus {rep} HTTP {r.status_code}")

        except requests.exceptions.Timeout:
            warnings.append(f"Cactus {rep} timeout")
        except Exception as exc:
            warnings.append(f"Cactus {rep} error: {exc}")

        time.sleep(RETRY_DELAY)

    return None