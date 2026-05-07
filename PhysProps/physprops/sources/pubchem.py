
"""
PubChem PUG-REST interface for retrieving experimental physical properties.

Outputs follow the FLAT naming scheme:

    experimental_<property>
    source_<property> = 'pubchem'

Multiple values per property:
    Option C — the first valid numeric value with a known unit
               (after unit normalization) is used.

All temperatures normalized to °C.
Vapor pressure normalized to Pa.
Critical pressure normalized to Pa.
Density normalized to g/mL.
Solubility normalized to mg/L.

No computed or fallback values are handled here.
"""

import time, os, re, logging, requests
from typing import Optional, Dict, Any, List, Callable
from urllib.parse import quote
from pathlib import Path
from .resolver_cache import ResolverCache
from physprops.sources import pubchem as pubchem_mod

_CACHE_STATS = {
    "hit_success": 0,
    "hit_negative": 0,
    "hit_temp": 0,
    "miss": 0,
    "net_success": 0,
    "net_400": 0,
    "net_404": 0,
    "net_temp": 0,
}

def _cache_path():
    root = os.environ.get("CANONICAL_DB_LOCAL_ROOT")
    if root:
        return Path(root) / "cache" / "resolver_cache.sqlite"
    return Path.home() / "AppData" / "Local" / "Lysning" / "Canonical_DB" / "cache" / "resolver_cache.sqlite"

_CACHE = ResolverCache(_cache_path())

TTL_NEG = 30 * 24 * 3600   # 30 days for 400/404
TTL_TEMP = 60 * 60         # 1 hour for 503/timeouts

SESSION = requests.Session()


logger = logging.getLogger(__name__)

PUBCHEM_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
PUBCHEM_VIEW_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug_view"


# ------------------------------------------------------------
# Normalizers
# ------------------------------------------------------------

def _normalize_temperature(raw_value) -> Optional[float]:
    """
    Normalize temperature values from PubChem to Celsius.

    Accepts units:
        - Celsius (°C, C)
        - Kelvin (K)
        - Fahrenheit (F, °F)
        - Degree symbols optional

    Returns:
        Temperature in Celsius (float) or None.
    """
    if raw_value is None:
        return None

    s = str(raw_value).strip()

    m = re.search(r'([-+]?\d+(\.\d+)?)\s*([Kk]|°?C|°?F|fahrenheit|celsius)?', s)
    if not m:
        return None

    value = float(m.group(1))
    unit = m.group(3)
    if unit:
        unit = unit.lower().replace("°", "").strip()

    if unit in (None, "", "c", "celsius"):
        return value
    if unit == "k":
        return value - 273.15
    if unit in ("f", "fahrenheit"):
        return (value - 32) * 5.0 / 9.0

    logger.warning("Unknown temperature unit '%s' in '%s', assuming Celsius.", unit, raw_value)
    return value


def _normalize_pressure(value, unit, warnings: List[str]) -> Optional[float]:
    """
    Strict normalization of any pressure value to Pascals (Pa).

    Accepted units:
        Pa, kPa, MPa, bar, atm, torr, mmHg

    Rules:
        - Numeric-only values rejected (ambiguous)
        - Unknown units rejected
        - Descriptive strings rejected

    Returns:
        float (Pa) or None
    """
    # Explicit unit
    if unit:
        u = str(unit).lower().strip()
        try:
            v = float(value)
        except Exception:
            warnings.append(f"Non-numeric pressure '{value} {unit}' discarded.")
            return None

        if u == "pa":
            return v
        if u == "kpa":
            return v * 1_000.0
        if u == "mpa":
            return v * 1_000_000.0
        if u == "bar":
            return v * 100_000.0
        if u == "atm":
            return v * 101_325.0
        if u in ("torr", "mmhg", "mm hg"):
            return v * 133.322

        warnings.append(f"Unrecognized pressure unit '{unit}', discarding.")
        return None

    # No explicit unit: detect strings like "45 MPa"
    s = str(value).strip().lower()
    m = re.match(r'^([-+]?\d+(\.\d+)?)\s*(pa|kpa|mpa|bar|atm|torr|mmhg)$', s)
    if m:
        return _normalize_pressure(float(m.group(1)), m.group(3), warnings)

    # Numeric only -> reject
    if re.match(r'^[-+]?\d+(\.\d+)?$', s):
        warnings.append(f"Pressure '{value}' without unit rejected.")
        return None

    warnings.append(f"Cannot interpret pressure '{value}', discarding.")
    return None


def _normalize_density(value, unit, warnings: List[str]) -> Optional[float]:
    """
    Normalize density values to g/mL.

    Accepted units:
        g/mL, g/cm3, g/cm^3, g/L, kg/m3, mg/mL, mg/L

    Strict behavior:
        - Reject descriptive or non-numeric values
        - If unit omitted, accept only if numeric and reasonable (0 < d < 5)

    Returns:
        float (g/mL) or None
    """
    if unit:
        u = str(unit).lower().strip()
        try:
            v = float(value)
        except Exception:
            warnings.append(f"Non-numeric density '{value} {unit}' discarded.")
            return None

        if u in ("g/ml", "g/cm3", "g/cm^3"):
            return v
        if u == "g/l":
            return v / 1000.0
        if u == "kg/m3":
            return v / 1000.0
        if u == "mg/ml":
            return v / 1000.0
        if u == "mg/l":
            return v / 1_000_000.0

        warnings.append(f"Unknown density unit '{unit}', discarding.")
        return None

    s = str(value).strip().lower()

    # numeric only: allow if plausible
    if re.match(r'^[-+]?\d+(\.\d+)?$', s):
        d = float(s)
        if 0 < d < 5:
            return d
        warnings.append(f"Numeric density '{d}' without unit rejected.")
        return None

    # embedded unit
    m = re.match(r'^([-+]?\d+(\.\d+)?)\s*(g/ml|g/cm3|g/cm\^3|g/l|kg/m3|mg/ml|mg/l)$', s)
    if m:
        return _normalize_density(float(m.group(1)), m.group(3).replace("cm^3", "cm^3"), warnings)

    warnings.append(f"Cannot interpret density '{value}', discarding.")
    return None


def _normalize_solubility(value, unit, warnings: List[str]) -> Optional[float]:
    """
    Strict normalization of water solubility to mg/L.

    Accepted:
        - mg/L
        - g/L
        - mg/mL
        - µg/mL (ug/mL)
        - mg/m3
        - ppm (≈ mg/L)
        - ppb (≈ µg/L -> mg/L)

    Rejected:
        - %, % w/v, % w/w
        - descriptive text
        - ranges ('5–10 mg/L')
        - numeric-only without unit
        - unknown units

    Returns:
        float (mg/L) or None
    """
    # Explicit unit
    if unit:
        u = str(unit).lower().strip()
        try:
            v = float(value)
        except Exception:
            warnings.append(f"Non-numeric solubility '{value} {unit}' discarded.")
            return None

        if u in ("mg/l", "mg per l", "mg per litre"):
            return v
        if u == "g/l":
            return v * 1000.0
        if u == "mg/ml":
            return v * 1000.0
        if u in ("ug/ml", "µg/ml"):
            return v  # 1 µg/mL == 1 mg/L
        if u == "mg/m3":
            return v / 1000.0
        if u == "ppm":
            return v
        if u == "ppb":
            return v / 1000.0

        if "%" in u or "percent" in u:
            warnings.append(f"Percentage solubility '{value} {unit}' rejected (strict mode).")
            return None

        warnings.append(f"Unknown solubility unit '{unit}', discarding.")
        return None

    # No explicit unit: try patterns like "10 mg/L"
    s = str(value).strip().lower()

    # reject ranges
    if re.search(r'[-–]\s*\d', s) or " to " in s:
        warnings.append(f"Range solubility '{value}' rejected (strict mode).")
        return None

    m = re.match(r'^([-+]?\d+(\.\d+)?)\s*(mg/l|g/l|mg/ml|ug/ml|µg/ml|mg/m3|ppm|ppb)$', s)
    if m:
        return _normalize_solubility(float(m.group(1)), m.group(3), warnings)

    if re.match(r'^[-+]?\d+(\.\d+)?$', s):
        warnings.append(f"Numeric solubility '{value}' without unit rejected.")
        return None

    warnings.append(f"Cannot interpret solubility '{value}', discarding.")
    return None


def _normalize_heat_of_vaporization(value, unit, warnings: List[str]) -> Optional[float]:
    """
    Strict normalization of heat of vaporization to kJ/mol.

    Accepted units:
        - kJ/mol
        - kcal/mol (converted -> kJ/mol)

    Returns:
        float (kJ/mol) or None
    """
    if unit:
        u = str(unit).lower().strip()
        try:
            v = float(value)
        except Exception:
            warnings.append(f"Non-numeric heat of vaporization '{value} {unit}' discarded.")
            return None

        if u in ("kj/mol", "kj per mol", "kjpermol"):
            return v
        if u in ("kcal/mol", "kcal per mol", "kcalpermol"):
            return v * 4.184

        if any(bad in u for bad in ("j/g", "cal/g", "kcal/g", "j per g", "ev")):
            warnings.append(f"Heat of vaporization unit '{unit}' rejected (strict mode).")
            return None

        warnings.append(f"Unknown heat of vaporization unit '{unit}', discarding.")
        return None

    s = str(value).strip().lower()
    m = re.match(r'^([-+]?\d+(\.\d+)?)\s*(kj/mol|kcal/mol)$', s)
    if m:
        return _normalize_heat_of_vaporization(float(m.group(1)), m.group(3), warnings)

    if re.match(r'^[-+]?\d+(\.\d+)?$', s):
        warnings.append(f"Heat of vaporization '{value}' without unit rejected.")
        return None

    warnings.append(f"Cannot interpret heat of vaporization '{value}', discarding.")
    return None


def _normalize_refractive_index(value, unit, warnings: List[str]) -> Optional[float]:
    """
    Normalize refractive index to a dimensionless float.

    Accepts:
        - pure numeric values (1.0 < n < 2.2)
        - strings like "1.402 at 20 °C"
        - range values ("1.40–1.42", "1.40 - 1.42", "1.40 to 1.42")
          -> averaged automatically

    Rejects:
        - descriptive text
        - values outside physical bounds
        - non-numeric and non-range values
    """
    s = str(value).strip().lower()

    # unit is irrelevant for refractive index; ignore but keep for signature compatibility
    _ = unit

    # Range patterns
    range_patterns = [
        r'^([-+]?\d+(\.\d+)?)\s*[-–]\s*([-+]?\d+(\.\d+)?)$',
        r'^([-+]?\d+(\.\d+)?)\s+to\s+([-+]?\d+(\.\d+)?)$'
    ]
    for pattern in range_patterns:
        m = re.match(pattern, s)
        if m:
            n1 = float(m.group(1))
            n2 = float(m.group(3))
            avg = (n1 + n2) / 2.0
            if 1.0 < avg < 2.2:
                return avg
            warnings.append(f"Refractive index range '{value}' out of bounds, rejected.")
            return None

    # Extract first numeric token
    m = re.search(r'([-+]?\d+(\.\d+)?)', s)
    if not m:
        warnings.append(f"Cannot interpret refractive index '{value}', discarding.")
        return None

    n = float(m.group(1))
    if 1.0 < n < 2.2:
        return n

    warnings.append(f"Refractive index '{value}' outside physical bounds, rejected.")
    return None


def _extract_temperature_qualifier(raw_text) -> Optional[float]:
    """
    Extract temperature qualifiers embedded in strings.

    Examples:
        "1.402 at 20 °C" -> 20
        "3 mmHg (20 C)" -> 20
        "50 mg/L at 298 K" -> 24.85
        "40 kJ/mol at 25C" -> 25

    Returns:
        float (°C) or None
    """
    if raw_text is None:
        return None

    s = str(raw_text).lower()

    m = re.search(r'(\d+(\.\d+)?)\s*(°?c|celsius)', s)
    if m:
        return float(m.group(1))

    m = re.search(r'(\d+(\.\d+)?)\s*k\b', s)
    if m:
        return float(m.group(1)) - 273.15

    return None


# ------------------------------------------------------------
# CID resolution
# ------------------------------------------------------------




def resolve_to_cid(identifier: str, id_type: str, retries: int = 3, delay: float = 0.8) -> Optional[int]:
    """
    Resolve any identifier to a PubChem CID, with local SQLite caching.
    """
    if not identifier:
        return None

    key_value = str(identifier).strip()
    if not key_value:
        return None
    
    if id_type == "inchikey":
        key_value = key_value.upper()

    
    if id_type == "cas":
        key_value = key_value.replace(" ", "")


    # quick garbage filter (helps a lot)
    lower = key_value.lower()
    if lower in {"nan", "none", "null", "rdkit", "pubchem", "cactus"}:
        return None

    # Cache check (per-item at DEBUG; summary via _CACHE_STATS)
    cached = _CACHE.get("pubchem", id_type, key_value)
    if cached:
        status, result, http_status, updated_utc = cached
        age = int(time.time()) - int(updated_utc)

        logger.debug(
            "PubChem CID cache hit: type=%s key=%r status=%s result=%r http=%s age_s=%d",
            id_type, key_value, status, result, http_status, age
        )

        # 1) Cached success (always valid)
        if status == "success" and result:
            _CACHE_STATS["hit_success"] += 1
            try:
                return int(result)
            except Exception:
                # malformed cached CID: treat as miss and fall through
                pass

        # 2) Cached negative (skip network within TTL_NEG)
        if status in ("not_found", "bad_request") and age < TTL_NEG:
            _CACHE_STATS["hit_negative"] += 1
            return None

        # 3) Cached temporary error (skip network within TTL_TEMP)
        if status == "temp_error" and age < TTL_TEMP:
            _CACHE_STATS["hit_temp"] += 1
            return None

        # Otherwise: cache entry is expired (or malformed) → treat as miss and continue to network
        _CACHE_STATS["miss"] += 1

    else:
        logger.debug("PubChem CID cache miss: type=%s key=%r", id_type, key_value)
        _CACHE_STATS["miss"] += 1

    # Build endpoint using URL-encoded key_value
    encoded = quote(key_value, safe="")
    mapping = {
        "cas":      f"compound/name/{encoded}/cids/JSON",
        "name":     f"compound/name/{encoded}/cids/JSON",
        "smiles":   f"compound/smiles/{encoded}/cids/JSON",
        "inchi":    f"compound/inchi/{encoded}/cids/JSON",
        "inchikey": f"compound/inchikey/{encoded}/cids/JSON",
    }

    endpoint = mapping.get(id_type)
    if endpoint is None:
        logger.error("Unsupported identifier type for PubChem: %s", id_type)
        return None

    url = f"{PUBCHEM_BASE}/{endpoint}"
    last_status = None

    for attempt in range(1, retries + 1):
        try:
            r = SESSION.get(url, timeout=10)
            last_status = r.status_code

            if r.status_code == 200:
                data = r.json()
                cids = data.get("IdentifierList", {}).get("CID")
                if cids:
                    cid = int(cids[0])
                    _CACHE.put("pubchem", id_type, key_value, "success", result=str(cid), http_status=200)
                    _CACHE_STATS["net_success"] += 1
                    logger.debug("PubChem CID resolved: type=%s key=%r cid=%s", id_type, key_value, cid)
                    return cid

                # 200 but no CID → treat as not_found-ish and cache (prevents repeated calls)
                _CACHE.put("pubchem", id_type, key_value, "not_found", result=None, http_status=200)
                _CACHE_STATS["net_404"] += 1  # treat like not-found for stats purposes
                logger.debug("PubChem CID 200-but-empty: type=%s key=%r", id_type, key_value)
                return None

            # Negative cache on 404/400 (do not retry)
            if r.status_code == 404:
                _CACHE.put("pubchem", id_type, key_value, "not_found", result=None, http_status=404)
                _CACHE_STATS["net_404"] += 1
                logger.debug("PubChem CID not found (404): type=%s key=%r", id_type, key_value)
                return None

            if r.status_code == 400:
                _CACHE.put("pubchem", id_type, key_value, "bad_request", result=None, http_status=400)
                _CACHE_STATS["net_400"] += 1
                logger.debug("PubChem CID bad request (400): type=%s key=%r", id_type, key_value)
                return None

            # Temporary-ish server side failures: retry
            if r.status_code >= 500:
                _CACHE_STATS["net_temp"] += 1

            logger.debug("PubChem CID request failed (%s), attempt %s", r.status_code, attempt)

        except Exception as e:
            # timeouts / connection aborted etc. → treat as temporary
            _CACHE_STATS["net_temp"] += 1
            logger.warning("CID resolution error: %s, attempt %s", e, attempt)
            last_status = 503  # classify for caching below

        time.sleep(delay)

    # If we exhausted retries, cache as temp_error to avoid hammering PubChem repeatedly
    _CACHE.put("pubchem", id_type, key_value, "temp_error", result=None, http_status=last_status)
    logger.debug("PubChem CID temp_error cached: type=%s key=%r last_http=%s", id_type, key_value, last_status)
    return None

# ------------------------------------------------------------
# PubChem record fetch + extraction helpers
# ------------------------------------------------------------

def _flatten_information(section: Dict[str, Any], out: List[Dict[str, Any]]) -> None:
    """Recursively flatten PUG-View-like sections collecting Information entries."""
    if not isinstance(section, dict):
        return

    infos = section.get("Information", [])
    if isinstance(infos, list):
        out.extend([i for i in infos if isinstance(i, dict)])

    subsections = section.get("Section", [])
    if isinstance(subsections, list):
        for sub in subsections:
            _flatten_information(sub, out)


def _fetch_pubchem_information(cid: int, warnings: List[str]) -> List[Dict[str, Any]]:
    """
    Try to fetch PubChem 'Information' records.

    Preference:
      1) PUG-View (Record/Section/Information) — best for experimental properties
      2) Fallback: PUG compound/cid JSON (best-effort, structure varies)

    Returns: list of Information dicts
    """
    # 1) PUG-View
    view_url = f"{PUBCHEM_VIEW_BASE}/data/compound/{cid}/JSON"
    try:
        r = requests.get(view_url, timeout=20)
        if r.status_code == 200:
            data = r.json()
            record = data.get("Record", {})
            infos: List[Dict[str, Any]] = []
            for sec in record.get("Section", []) or []:
                _flatten_information(sec, infos)
            if infos:
                return infos
    except Exception as e:
        warnings.append(f"PUG-View fetch error: {e}")

    # 2) Fallback: compound/cid
    url = f"{PUBCHEM_BASE}/compound/cid/{cid}/JSON"
    try:
        r = requests.get(url, timeout=20)
        if r.status_code != 200:
            warnings.append(f"PubChem property request failed ({r.status_code}).")
            return []

        data = r.json()
        # Structure varies; best effort
        infos: List[Dict[str, Any]] = []

        compounds = data.get("PC_Compounds") or []
        if compounds and isinstance(compounds, list):
            # Some responses don't contain sections at all; return empty if absent
            sec = compounds[0].get("Section")
            if isinstance(sec, list):
                for s in sec:
                    _flatten_information(s, infos)

        return infos
    except Exception as e:
        warnings.append(f"PubChem compound fetch error: {e}")
        return []


def _extract_first_valid_value(
    info_list: List[dict],
    property_keywords: List[str],
    warnings: List[str]
) -> Optional[Dict[str, Any]]:
    """
    Scan PubChem 'Information' entries and extract the first numeric value
    whose Name contains any of the keywords.

    Returns:
      {"value": <raw numeric or string>, "unit": <unit or None>, "text": <original text>}
    """
    for info in info_list:
        name = str(info.get("Name", "")).lower()
        if not any(key in name for key in property_keywords):
            continue

        value_obj = info.get("Value", {})
        if not isinstance(value_obj, dict):
            continue

        # Most common shapes:
        #  - {"Number": 123.4, "Unit": "kPa"}
        #  - {"String": "1.402 at 20 C"}
        #  - {"StringWithMarkup": [{"String": "..."}], ...}

        if "Number" in value_obj:
            unit = value_obj.get("Unit")
            number = value_obj.get("Number")

            # PubChem sometimes returns lists of numbers
            if isinstance(number, (list, tuple)):
                number = next((x for x in number if isinstance(x, (int, float))), None)

            text = f"{number} {unit}" if unit else str(number)
            return {"value": number, "unit": unit, "text": text}

        if "String" in value_obj:
            s = value_obj.get("String")
            return {"value": s, "unit": None, "text": str(s)}

        swm = value_obj.get("StringWithMarkup")
        if isinstance(swm, list) and swm:
            s = swm[0].get("String")
            if s is not None:
                return {"value": s, "unit": None, "text": str(s)}

    return None


# ------------------------------------------------------------
# Top-level PubChem property retrieval
# ------------------------------------------------------------

def get_pubchem_properties(identifier: str, id_type: str) -> Dict[str, Any]:
    """
    Retrieve experimental physical properties from PubChem.

    Output is FLAT:

        experimental_<property>
        source_<property> = "pubchem"

    If no data: value remains None, source remains None.
    """
    warnings: List[str] = []

    result: Dict[str, Any] = {
        # Temperatures (°C)
        "experimental_boiling_point_c": None,
        "source_boiling_point_c": None,

        "experimental_melting_point_c": None,
        "source_melting_point_c": None,

        "experimental_flash_point_c": None,
        "source_flash_point_c": None,

        "experimental_autoignition_temp_c": None,
        "source_autoignition_temp_c": None,

        "experimental_critical_temp_c": None,
        "source_critical_temp_c": None,

        # Pressure (Pa)
        "experimental_vapor_pressure_pa": None,
        "source_vapor_pressure_pa": None,

        "experimental_critical_pressure_pa": None,
        "source_critical_pressure_pa": None,

        # Other physical properties
        "experimental_density_g_ml": None,
        "source_density_g_ml": None,

        "experimental_refractive_index": None,
        "source_refractive_index": None,

        "experimental_water_solubility_mg_l": None,
        "source_water_solubility_mg_l": None,

        "experimental_logp": None,
        "source_logp": None,

        "experimental_heat_of_vaporization_kj_mol": None,
        "source_heat_of_vaporization_kj_mol": None,

        # Temperature qualifiers (°C) if embedded ("at 20 C", etc.)
        "experimental_boiling_point_c_temperature_c": None,
        "experimental_melting_point_c_temperature_c": None,
        "experimental_flash_point_c_temperature_c": None,
        "experimental_autoignition_temp_c_temperature_c": None,
        "experimental_critical_temp_c_temperature_c": None,
        "experimental_vapor_pressure_pa_temperature_c": None,
        "experimental_critical_pressure_pa_temperature_c": None,
        "experimental_density_g_ml_temperature_c": None,
        "experimental_refractive_index_temperature_c": None,
        "experimental_water_solubility_mg_l_temperature_c": None,
        "experimental_heat_of_vaporization_kj_mol_temperature_c": None,
        "experimental_logp_temperature_c": None,

        "warnings": warnings,
    }

    # 1) CID resolution
    cid = resolve_to_cid(identifier, id_type)
    if cid is None:
        warnings.append("PubChem CID resolution failed.")
        return result

    # 2) Fetch information entries
    info_list = _fetch_pubchem_information(cid, warnings)
    if not info_list:
        warnings.append("PubChem returned no usable Information records.")
        return result

    # helper to assign
    def assign(
        prop_name: str,
        keywords: List[str],
        unit_handler: Optional[Callable[[Any, Any, List[str]], Optional[float]]] = None,
    ) -> None:
        entry = _extract_first_valid_value(info_list, keywords, warnings)
        if entry is None:
            return

        raw_value = entry["value"]
        raw_unit = entry["unit"]
        raw_text = entry.get("text", raw_value)

        qualifier_temp = _extract_temperature_qualifier(raw_text)

        # normalize
        if unit_handler:
            value = unit_handler(raw_value, raw_unit, warnings)
        else:
            # best effort cast
            try:
                value = float(raw_value)
            except Exception:
                value = raw_value

        result[f"experimental_{prop_name}"] = value
        result[f"source_{prop_name}"] = "pubchem"

        if qualifier_temp is not None:
            result[f"experimental_{prop_name}_temperature_c"] = qualifier_temp

    # Temperatures
    assign("boiling_point_c", ["boiling"], lambda v, u, w: _normalize_temperature(f"{v} {u}" if u else v))
    assign("melting_point_c", ["melting"], lambda v, u, w: _normalize_temperature(f"{v} {u}" if u else v))
    assign("flash_point_c", ["flash"], lambda v, u, w: _normalize_temperature(f"{v} {u}" if u else v))
    assign("autoignition_temp_c", ["autoignition"], lambda v, u, w: _normalize_temperature(f"{v} {u}" if u else v))
    assign("critical_temp_c", ["critical temperature"], lambda v, u, w: _normalize_temperature(f"{v} {u}" if u else v))

    # Pressures
    assign("vapor_pressure_pa", ["vapor pressure"], lambda v, u, w: _normalize_pressure(v, u, w))
    assign("critical_pressure_pa", ["critical pressure"], lambda v, u, w: _normalize_pressure(v, u, w))

    # Other props
    assign("density_g_ml", ["density"], lambda v, u, w: _normalize_density(v, u, w))
    assign("refractive_index", ["refractive index"], lambda v, u, w: _normalize_refractive_index(v, u, w))
    assign("water_solubility_mg_l", ["water solubility", "aqueous solubility"], lambda v, u, w: _normalize_solubility(v, u, w))
    assign("logp", ["logp", "log p"], None)
    assign("heat_of_vaporization_kj_mol", ["heat of vaporization"], lambda v, u, w: _normalize_heat_of_vaporization(v, u, w))

    return result
