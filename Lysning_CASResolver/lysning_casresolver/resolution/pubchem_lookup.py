import logging
import time
import requests

logger = logging.getLogger(__name__)

PUBCHEM_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
TIMEOUT = 10  # seconds
RETRIES = 3
RETRY_DELAY = 1.5  # seconds


def resolve_pubchem_cas(cas: str) -> dict | None:
    """
    Resolve CAS via PubChem PUG-REST.

    Workflow:
      1. CAS → CID lookup
      2. CID → properties (IsomericSMILES, InChI, MolecularWeight)
      3. Parse + return unified structure

    Returns
    -------
    dict | None
        {
            "smiles": "...",
            "inchi": "...",
            "inchikey": "...",
            "mw": float,
            "warning_list": [...],
            "timestamp": "...Z"
        }
        or None if not found or all attempts fail.
    """
    warnings = []
    try:
        cid = _pubchem_cas_to_cid(cas, warnings)
        if not cid:
            warnings.append("PubChem: no CID found")
            return None

        data = _pubchem_fetch_properties(cid, warnings)
        if not data:
            warnings.append("PubChem: property fetch failed")
            return None

        return data

    except Exception as exc:
        logger.debug("PubChem lookup crashed for CAS %s: %s", cas, exc)
        warnings.append(f"PubChem crash: {exc}")
        return None


# --------------------------------------------------------------------
# INTERNAL FUNCTIONS
# --------------------------------------------------------------------

def _pubchem_cas_to_cid(cas: str, warnings: list) -> str | None:
    """
    Step 1: CAS → CID.

    Parameters
    ----------
    cas : str
    warnings : list
        Accumulates warnings.

    Returns
    -------
    str | None
    """
    url = f"{PUBCHEM_BASE}/compound/name/{cas}/cids/JSON"

    for attempt in range(RETRIES):
        try:
            logger.debug("PubChem CID fetch attempt %d for CAS %s", attempt + 1, cas)
            r = requests.get(url, timeout=TIMEOUT)
            if r.status_code == 200:
                data = r.json()
                cids = data.get("IdentifierList", {}).get("CID", [])
                if cids:
                    return str(cids[0])
                return None
            elif r.status_code == 404:
                return None
            else:
                warnings.append(f"CID lookup HTTP {r.status_code}")
        except requests.exceptions.Timeout:
            warnings.append("CID lookup timeout")
        except Exception as exc:
            warnings.append(f"CID lookup error: {exc}")

        time.sleep(RETRY_DELAY)

    return None


def _pubchem_fetch_properties(cid: str, warnings: list) -> dict | None:
    """
    Step 2: fetch properties for a CID.

    Requests:
      - canonical smiles (IsomericSMILES)
      - InChI
      - MolecularWeight
      - InChIKey

    Parameters
    ----------
    cid : str
    warnings : list

    Returns
    -------
    dict | None
    """
    url = (
        f"{PUBCHEM_BASE}/compound/cid/{cid}/property/"
        "IsomericSMILES,InChI,InChIKey,MolecularWeight/JSON"
    )

    for attempt in range(RETRIES):
        try:
            logger.debug("PubChem property fetch attempt %d for CID %s", attempt + 1, cid)
            r = requests.get(url, timeout=TIMEOUT)
            if r.status_code == 200:
                return _parse_property_result(r.json(), warnings)
            elif r.status_code == 404:
                warnings.append("CID not found for properties")
                return None
            else:
                warnings.append(f"Property fetch HTTP {r.status_code}")

        except requests.exceptions.Timeout:
            warnings.append("property fetch timeout")
        except Exception as exc:
            warnings.append(f"property fetch error: {exc}")

        time.sleep(RETRY_DELAY)

    return None


def _parse_property_result(data: dict, warnings: list) -> dict | None:
    """
    Extracts SMILES, InChI, MW, InChIKey.

    Parameters
    ----------
    data : dict
    warnings : list

    Returns
    -------
    dict | None
    """
    props = data.get("PropertyTable", {}).get("Properties", [])
    if not props:
        warnings.append("no property table")
        return None

    p = props[0]

    smiles = p.get("IsomericSMILES", "")
    inchi = p.get("InChI", "")
    inchikey = p.get("InChIKey", "")
    mw = p.get("MolecularWeight")

    if not smiles and not inchi:
        warnings.append("missing SMILES/InChI")
        return None

    try:
        mw = float(mw) if mw is not None else None
    except Exception:
        warnings.append("MW conversion issue")
        mw = None

    return {
        "smiles": smiles,
        "inchi": inchi,
        "inchikey": inchikey,
        "mw": mw,
        "warning_list": warnings[:],
        "timestamp": None,  # filled by orchestrator
    }