import logging
import os
import time
import requests
from datetime import datetime

logger = logging.getLogger(__name__)

CHEMSPIDER_BASE = "https://api.rsc.org/compounds/v1"
TIMEOUT = 15
RETRIES = 3
RETRY_DELAY = 2.0


def resolve_chemspider_cas(cas: str) -> dict | None:
    """
    Resolve CAS using ChemSpider API.

    Workflow:
      1. CAS → search task
      2. poll until Complete
      3. retrieve result list
      4. fetch details for first record
      5. extract SMILES / InChI / MW

    Requires environment variable:
        CHEMSPIDER_API_KEY

    Returns
    -------
    dict | None
        Structured result or None if not found.
    """
    warnings = []
    api_key = os.environ.get("5DmhIUQRj14nK1DO76Rph17ouhyrO1g5iqZcQ1q9")

    if not api_key:
        warnings.append("ChemSpider API key missing")
        logger.debug("ChemSpider API key not set.")
        return None

    try:
        # 1. submit search task
        task_id = _chemspider_submit_search(api_key, cas, warnings)
        if not task_id:
            warnings.append("ChemSpider: no task ID")
            return None

        # 2. poll for completion
        status = _chemspider_poll(api_key, task_id, warnings)
        if status != "Complete":
            warnings.append(f"ChemSpider: search not complete ({status})")
            return None

        # 3. retrieve results
        csids = _chemspider_fetch_results(api_key, task_id, warnings)
        if not csids:
            warnings.append("ChemSpider: no CSIDs returned")
            return None

        csid = csids[0]  # pick first
        logger.debug("ChemSpider returned CSID %s for CAS %s", csid, cas)

        # 4. fetch details
        details = _chemspider_fetch_details(api_key, csid, warnings)
        if not details:
            warnings.append("ChemSpider: detail retrieval failed")
            return None

        return {
            "smiles": details.get("smiles", ""),
            "inchi": details.get("inchi", ""),
            "inchikey": details.get("inchikey", ""),
            "mw": details.get("mw", None),
            "warning_list": warnings[:],
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

    except Exception as exc:
        logger.debug("ChemSpider lookup crashed for CAS %s: %s", cas, exc)
        warnings.append(f"ChemSpider crash: {exc}")
        return None


# --------------------------------------------------------------------
# INTERNAL FUNCTIONS
# --------------------------------------------------------------------

def _chemspider_submit_search(api_key: str, cas: str, warnings: list) -> str | None:
    """Submit CAS search → returns task ID."""
    url = f"{CHEMSPIDER_BASE}/filter/name"
    payload = {"name": cas}
    headers = {"apikey": api_key}

    for attempt in range(RETRIES):
        try:
            r = requests.post(url, json=payload, headers=headers, timeout=TIMEOUT)
            if r.status_code == 200:
                task_id = r.json().get("taskId")
                return task_id
            else:
                warnings.append(f"ChemSpider search HTTP {r.status_code}")
        except requests.exceptions.Timeout:
            warnings.append("ChemSpider search timeout")
        except Exception as exc:
            warnings.append(f"ChemSpider search error: {exc}")

        time.sleep(RETRY_DELAY)

    return None


def _chemspider_poll(api_key: str, task_id: str, warnings: list) -> str | None:
    """Poll ChemSpider task status until Complete."""
    url = f"{CHEMSPIDER_BASE}/tasks/{task_id}"
    headers = {"apikey": api_key}

    for _ in range(15):  # max ~30 seconds
        try:
            r = requests.get(url, headers=headers, timeout=TIMEOUT)
            if r.status_code == 200:
                status = r.json().get("status")
                if status == "Complete":
                    return status
                elif status in ("Failed", "Expired"):
                    warnings.append(f"ChemSpider task {status}")
                    return status
                time.sleep(2)
            else:
                warnings.append(f"ChemSpider poll HTTP {r.status_code}")
        except Exception as exc:
            warnings.append(f"ChemSpider poll error: {exc}")
            time.sleep(RETRY_DELAY)

    warnings.append("ChemSpider polling timeout")
    return "Timeout"


def _chemspider_fetch_results(api_key: str, task_id: str, warnings: list) -> list | None:
    """Retrieve result CSIDs."""
    url = f"{CHEMSPIDER_BASE}/filter/{task_id}/results"
    headers = {"apikey": api_key}

    try:
        r = requests.get(url, headers=headers, timeout=TIMEOUT)
        if r.status_code == 200:
            return r.json().get("results", [])
        else:
            warnings.append(f"ChemSpider results HTTP {r.status_code}")
    except Exception as exc:
        warnings.append(f"ChemSpider results error: {exc}")

    return None


def _chemspider_fetch_details(api_key: str, csid: str, warnings: list):
    """Fetch full properties for a CSID."""
    url = f"{CHEMSPIDER_BASE}/records/{csid}/details"
    headers = {"apikey": api_key}
    params = {"fields": "SMILES,InChI,InChIKey,MolecularWeight"}

    try:
        r = requests.get(url, headers=headers, params=params, timeout=TIMEOUT)
        if r.status_code == 200:
            return _parse_detail(r.json(), warnings)
        else:
            warnings.append(f"ChemSpider detail HTTP {r.status_code}")
    except Exception as exc:
        warnings.append(f"ChemSpider detail error: {exc}")

    return None


def _parse_detail(data: dict, warnings: list) -> dict | None:
    """Extract structure info from ChemSpider detail JSON."""
    try:
        smiles = data.get("smiles", "")
        inchi = data.get("inchi", "")
        inchikey = data.get("inchikey", "")
        mw = data.get("molecularWeight")

        try:
            mw = float(mw) if mw is not None else None
        except Exception:
            warnings.append("ChemSpider MW conversion issue")
            mw = None

        if not smiles and not inchi:
            warnings.append("ChemSpider: missing SMILES/InChI")
            return None

        return {
            "smiles": smiles,
            "inchi": inchi,
            "inchikey": inchikey,
            "mw": mw,
        }

    except Exception as exc:
        warnings.append(f"ChemSpider parsing error: {exc}")
        return None