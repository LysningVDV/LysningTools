import logging
import time
import requests

logger = logging.getLogger(__name__)

PUBCHEM_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
TIMEOUT = 10
RETRIES = 3
RETRY_DELAY = 1.5


# ---------------------------------------------------------------------
# NAME → CID LIST
# ---------------------------------------------------------------------

def fetch_cids_for_name(name: str, warnings: list) -> list[str]:
    """
    Query PubChem to convert a chemical name into a list of CIDs.

    Parameters
    ----------
    name : str
        Normalized chemical name.

    warnings : list
        A shared list to accumulate warnings.

    Returns
    -------
    list of str
        A list of CID numbers as strings. May be empty on failure or no match.
    """
    url = f"{PUBCHEM_BASE}/compound/name/{name}/cids/JSON"

    for attempt in range(RETRIES):
        try:
            logger.debug("PubChem name→CID attempt %d for '%s'", attempt + 1, name)
            r = requests.get(url, timeout=TIMEOUT)

            if r.status_code == 200:
                data = r.json()
                cids = data.get("IdentifierList", {}).get("CID", [])
                cids = [str(c) for c in cids]
                logger.debug("PubChem returned CIDs %s for '%s'", cids, name)
                return cids

            elif r.status_code == 404:
                return []

            else:
                warnings.append(f"name→CID HTTP {r.status_code}")
                logger.debug("PubChem name→CID HTTP %s for '%s'", r.status_code, name)

        except requests.exceptions.Timeout:
            warnings.append("name→CID timeout")
        except Exception as exc:
            warnings.append(f"name→CID error: {exc}")

        time.sleep(RETRY_DELAY)

    return []


# ---------------------------------------------------------------------
# CID → PROPERTIES
# ---------------------------------------------------------------------

def fetch_properties_for_cid(cid: str, warnings: list) -> dict | None:
    """
    Fetch structural properties for a given PubChem CID.

    Retrieves:
        - SMILES
        - InChI
        - InChIKey
        - MW
        - Synonyms

    Returns None if the CID cannot supply usable structure data.

    Parameters
    ----------
    cid : str
    warnings : list

    Returns
    -------
    dict or None:
        {
            "cid": str,
            "smiles": str,
            "inchi": str,
            "inchikey": str,
            "mw": float or None,
            "synonyms": [str, str, ...]
        }
    """
    props = _fetch_main_properties(cid, warnings)
    if not props:
        return None

    synonyms = _fetch_synonyms(cid, warnings)
    props["synonyms"] = synonyms
    return props


# ---------------------------------------------------------------------
# Helper: fetch SMILES / InChI / MW
# ---------------------------------------------------------------------

def _fetch_main_properties(cid: str, warnings: list) -> dict | None:
    url = (f"{PUBCHEM_BASE}/compound/cid/{cid}/property/"
           "IsomericSMILES,InChI,InChIKey,MolecularWeight/JSON")

    for attempt in range(RETRIES):
        try:
            logger.debug("PubChem CID→properties attempt %d for CID %s", attempt + 1, cid)
            r = requests.get(url, timeout=TIMEOUT)

            if r.status_code == 200:
                pt = r.json().get("PropertyTable", {}).get("Properties", [])
                if not pt:
                    warnings.append(f"CID {cid}: no property table")
                    return None

                p = pt[0]
                smiles = p.get("IsomericSMILES", "")
                inchi = p.get("InChI", "")
                inchikey = p.get("InChIKey", "")
                mw = p.get("MolecularWeight", None)

                try:
                    mw = float(mw) if mw is not None else None
                except Exception:
                    warnings.append(f"CID {cid}: MW parsing error")
                    mw = None

                if not smiles and not inchi:
                    warnings.append(f"CID {cid}: missing SMILES/InChI")
                    return None

                return {
                    "cid": cid,
                    "smiles": smiles or "",
                    "inchi": inchi or "",
                    "inchikey": inchikey or "",
                    "mw": mw
                }

            elif r.status_code == 404:
                warnings.append(f"CID {cid}: not found for properties")
                return None

            else:
                warnings.append(f"CID {cid} property HTTP {r.status_code}")

        except requests.exceptions.Timeout:
            warnings.append(f"CID {cid}: properties timeout")
        except Exception as exc:
            warnings.append(f"CID {cid}: properties error: {exc}")

        time.sleep(RETRY_DELAY)

    return None


# ---------------------------------------------------------------------
# Helper: fetch synonyms for ranking
# ---------------------------------------------------------------------

def _fetch_synonyms(cid: str, warnings: list) -> list[str]:
    url = f"{PUBCHEM_BASE}/compound/cid/{cid}/synonyms/JSON"
    synonyms = []

    for attempt in range(RETRIES):
        try:
            logger.debug("PubChem CID→synonyms attempt %d for CID %s", attempt + 1, cid)
            r = requests.get(url, timeout=TIMEOUT)

            if r.status_code == 200:
                info = r.json().get("InformationList", {}).get("Information", [])
                if info:
                    synonyms = info[0].get("Synonym", []) or []
                return synonyms

            elif r.status_code == 404:
                return []

            else:
                warnings.append(f"CID {cid} synonyms HTTP {r.status_code}")

        except requests.exceptions.Timeout:
            warnings.append(f"CID {cid}: synonyms timeout")
        except Exception as exc:
            warnings.append(f"CID {cid}: synonyms error: {exc}")

        time.sleep(RETRY_DELAY)

    return synonyms