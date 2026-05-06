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
Density normalized to g/mL.
Solubility normalized to mg/L.

No computed or fallback values are handled here.
"""

import logging
import time
from typing import Optional, Dict, Any, List

import requests
from physprops.util.normalize import normalize_pubchem_unit

logger = logging.getLogger(__name__)

PUBCHEM_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"


# ------------------------------------------------------------
# CID resolution
# ------------------------------------------------------------

def resolve_to_cid(identifier: str, id_type: str, retries: int = 3, delay: float = 0.8) -> Optional[int]:
    """
    Resolve any identifier to a PubChem CID.
    """

    if identifier is None:
        return None

    mapping = {
        "cas":       f"compound/name/{identifier}/cids/JSON",
        "name":      f"compound/name/{identifier}/cids/JSON",
        "smiles":    f"compound/smiles/{identifier}/cids/JSON",
        "inchi":     f"compound/inchi/{identifier}/cids/JSON",
        "inchikey":  f"compound/inchikey/{identifier}/cids/JSON",
    }

    endpoint = mapping.get(id_type)
    if endpoint is None:
        logger.error(f"Unsupported identifier type for PubChem: {id_type}")
        return None

    url = f"{PUBCHEM_BASE}/{endpoint}"

    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                data = r.json()
                cids = data.get("IdentifierList", {}).get("CID")
                if cids:
                    return cids[0]
                return None

            logger.warning(f"PubChem CID request failed ({r.status_code}), attempt {attempt}")

        except Exception as e:
            logger.warning(f"CID resolution error: {e}, attempt {attempt}")

        time.sleep(delay)

    return None


# ------------------------------------------------------------
# Helpers to extract the “first good numeric value”
# ------------------------------------------------------------

def _extract_first_valid_value(info_list: List[dict], property_keywords: List[str],
                               warnings: List[str]) -> Optional[Dict[str, Any]]:
    """
    Scan a list of PubChem 'Information' entries and extract the first numeric value
    whose 'Name' contains any of the keywords.

    Returns:
      { "value": float, "unit": str or None }
    or None if nothing valid found.
    """

    for info in info_list:
        name = info.get("Name", "").lower()
        if not any(key in name for key in property_keywords):
            continue

        value = info.get("Value", {})

        # Try numeric extraction
        if "Number" in value:
            return {"value": value["Number"], "unit": value.get("Unit")}

        # Try parsing "String" field as float
        if "String" in value:
            try:
                val = float(value["String"])
                return {"value": val, "unit": None}
            except:
                continue

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

    # Initialize flat dictionary with all experimental properties
    result = {
        # Temperatures
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

        # Pressure
        "experimental_vapor_pressure_pa": None,
        "source_vapor_pressure_pa": None,

        "experimental_critical_pressure_bar": None,
        "source_critical_pressure_bar": None,

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

        "warnings": warnings
    }

    # ---------------------------------------------------------
    # 1. CID resolution
    # ---------------------------------------------------------
    cid = resolve_to_cid(identifier, id_type)
    if cid is None:
        warnings.append("PubChem CID resolution failed.")
        return result

    url = f"{PUBCHEM_BASE}/compound/cid/{cid}/JSON"

    try:
        r = requests.get(url, timeout=15)
        if r.status_code != 200:
            warnings.append(f"PubChem property request failed ({r.status_code}).")
            return result

        data = r.json()
        records = data.get("PC_Compounds")
        if not records:
            warnings.append("PubChem returned no compound records.")
            return result

        record = records[0]
        sections = record.get("Section", [])

        # -----------------------------------------------------
        # Extract properties by scanning all sections
        # -----------------------------------------------------
        # Build a unified list of all Information records
        all_info = []
        for sec in sections:
            all_info.extend(sec.get("Information", []))

        # Helper to assign a property
        def assign(prop_name: str, keywords: List[str], unit_handler=None):
            entry = _extract_first_valid_value(all_info, keywords, warnings)
            if entry is None:
                return

            value = entry["value"]
            unit = entry["unit"]

            if unit_handler:
                value = unit_handler(value, unit, warnings)

            result[f"experimental_{prop_name}"] = value
            result[f"source_{prop_name}"] = "pubchem"

        # -----------------------------------------------------
        # Map properties (Option C – take first valid numeric)
        # -----------------------------------------------------

        assign("boiling_point_c", ["boiling"], normalize_pubchem_unit)
        assign("melting_point_c", ["melting"], normalize_pubchem_unit)
        assign("flash_point_c", ["flash"], normalize_pubchem_unit)
        assign("autoignition_temp_c", ["autoignition"], normalize_pubchem_unit)
        assign("critical_temp_c", ["critical temperature"], normalize_pubchem_unit)

        assign("vapor_pressure_pa", ["vapor pressure"], normalize_pubchem_unit)

        assign("density_g_ml", ["density"], 
               lambda v, u, w: normalize_pubchem_unit(v, u, w) if u else v)

        assign("refractive_index", ["refractive index"], lambda v, u, w: v)

        # Water solubility special handling
        def solubility_norm(v, u, w):
            if u is None:
                return v
            uu = u.lower()
            if uu in ["mg/l", "mg per l"]:
                return v
            w.append(f"Unrecognized solubility unit '{u}', value kept.")
            return v

        assign("water_solubility_mg_l", ["water solubility"], solubility_norm)

        # logP (experimental)
        assign("logp", ["logp", "log p"], lambda v, u, w: v)

        # Heat of vaporization
        def heat_norm(v, u, w):
            if u is None:
                return v
            if u.lower() in ["kj/mol", "kj per mol"]:
                return v
            w.append(f"Unknown heat of vaporization unit '{u}'")
            return v

        assign("heat_of_vaporization_kj_mol", ["heat of vaporization"], heat_norm)

        # Critical pressure
        def crit_p_norm(v, u, w):
            if u is None:
                return v
            u = u.lower()
            if u == "bar":
                return v
            if u == "pa":
                return v / 100000.0
            w.append(f"Unknown critical pressure unit '{u}'")
            return v

        assign("critical_pressure_bar", ["critical pressure"], crit_p_norm)

        return result

    except Exception as e:
        warnings.append(f"PubChem request error: {e}")
        return result