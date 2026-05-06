# physprops/canonical/mapper.py
from __future__ import annotations

from typing import Any, Dict, List, Tuple
import math

from physprops.canonical.units import (
    pressure_to_pa,
    temperature_to_c,
    density_to_g_ml,
    solubility_to_mg_l,
)
from physprops.util.normalize import is_null, as_float


# ------------------------------------------------------------
# helpers
# ------------------------------------------------------------

def _append_warning(warnings: List[str], msg: str) -> None:
    msg = str(msg).strip()
    if not msg:
        return
    warnings.append(msg)


def log10_or_none(x: Any) -> float | None:
    v = as_float(x)
    if v is None:
        return None
    try:
        if v <= 0:
            return None
        return float(math.log10(v))
    except Exception:
        return None


def _temp_status(wide_row: Dict[str, Any], temp_col: str) -> str:
    """
    Return status of 25C metadata for a property:
      - 'missing'     : no temperature metadata column
      - 'blank'       : column exists but value missing
      - '25'          : temperature approx 25C
      - 'not_25'      : temperature present but not 25C
      - 'invalid'     : temperature present but not parseable
    """
    if temp_col not in wide_row:
        return "missing"
    v = wide_row.get(temp_col)
    if is_null(v):
        return "blank"
    tv = as_float(v)
    if tv is None:
        return "invalid"
    if abs(tv - 25.0) <= 1.0:
        return "25"
    return "not_25"


def _flag_25c_if_needed(flags: List[str], *, prop_name: str, prop_value: Any, temp_status: str) -> None:
    if prop_value is None:
        return
    # Only flag missing or not_25. Do not flag blank (assume unknown).
    if temp_status in ("missing", "not_25", "invalid"):
        flags.append(f"{prop_name}:{temp_status}")


def _pick_logp(wide_row: Dict[str, Any]) -> Tuple[float | None, str | None]:
    """
    Deterministic pick of logP for canonical:
      - prefer final_logp if present
      - else use final_clogp (computed) if present
    Returns (value, source_column_name)
    """
    v = as_float(wide_row.get("final_logp"))
    if v is not None:
        return v, "source_logp"
    v2 = as_float(wide_row.get("final_clogp"))
    if v2 is not None:
        return v2, "source_clogp"
    return None, None


def _summarize_sources(wide_row: Dict[str, Any], logp_source_col: str | None) -> Tuple[str | None, str | None]:
    """
    Summarize primary/secondary sources based on explicit source_* fields.
    """
    sources: List[str] = []

    # A small deterministic set used for summarization (aligned with builder scoring)
    source_cols = [
        "source_mw",
        "source_tpsa",
        "source_boiling_point_c",
        "source_vapor_pressure_pa",
        "source_density_g_ml",
        "source_water_solubility_mg_l",
    ]
    if logp_source_col:
        source_cols.append(logp_source_col)

    for c in source_cols:
        s = wide_row.get(c)
        if not is_null(s):
            ss = str(s).strip()
            if ss and ss not in sources:
                sources.append(ss)

    if not sources:
        return None, None

    primary = sources[0]
    secondary = sources[1] if len(sources) > 1 else None
    return primary, secondary


# ------------------------------------------------------------
# canonical row mapping
# ------------------------------------------------------------

def build_canonical_row(wide_row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build ONE canonical physprops row from ONE wide output row.

    Final rules implemented:
      - log_vapor_pressure = log10(vapor_pressure_Pa_25C)
      - log_water_solubility = log10(water_solubility_mg_L_25C)
      - retain values but flag if 25C note missing or not 25C (for VP, density, solubility)
      - convert explicit-unit strings to canonical units:
          VP -> Pa, temps -> °C, density -> g/mL, solubility -> mg/L (ppm treated as mg/L with warning)
      - do NOT flag when numeric values have no unit metadata (assume upstream normalization)
      - key = inchi_key (from final_inchikey)
    """

    # --- Required key ---
    inchi_key = wide_row.get("final_inchikey")
    if is_null(inchi_key):
        return {}

    warnings: List[str] = []
    if not is_null(wide_row.get("warnings")):
        _append_warning(warnings, str(wide_row.get("warnings")))

    # --- Identity ---
    cas_number = wide_row.get("CAS_ID")
    smiles = wide_row.get("final_smiles")

    name_preferred = None
    if str(wide_row.get("identifier_type", "")).strip().lower() == "name":
        name_preferred = wide_row.get("normalized_input")

    # --- Descriptors ---
    mw = as_float(wide_row.get("final_mw"))
    tpsa = as_float(wide_row.get("final_tpsa"))
    logp, logp_source_col = _pick_logp(wide_row)

    # Not available in the current wide output -> keep None
    num_heavy_atoms = None

    # --- Physprops with unit conversion (explicit units only) ---
    boiling_point_c = temperature_to_c(wide_row.get("final_boiling_point_c"), warnings=warnings)
    melting_point_c = temperature_to_c(wide_row.get("final_melting_point_c"), warnings=warnings)

    vapor_pressure_pa = pressure_to_pa(wide_row.get("final_vapor_pressure_pa"), warnings=warnings)
    density_g_ml = density_to_g_ml(wide_row.get("final_density_g_ml"), warnings=warnings)

    water_solubility_mg_l = solubility_to_mg_l(
        wide_row.get("final_water_solubility_mg_l"),
        mw_g_mol=mw,
        warnings=warnings,
        assume_ppm_mg_l=True,  # Option 1 locked in
    )

    # --- log10 fields (frozen) ---
    log_vapor_pressure = log10_or_none(vapor_pressure_pa)
    log_water_solubility = log10_or_none(water_solubility_mg_l)

    # --- 25C metadata checks: retain values but flag missing / !=25 ---
    vp_ts = _temp_status(wide_row, "experimental_vapor_pressure_pa_temperature_c")
    dens_ts = _temp_status(wide_row, "experimental_density_g_ml_temperature_c")
    sol_ts = _temp_status(wide_row, "experimental_water_solubility_mg_l_temperature_c")

    temp_flags: List[str] = []
    _flag_25c_if_needed(temp_flags, prop_name="vapor_pressure_Pa_25C", prop_value=vapor_pressure_pa, temp_status=vp_ts)
    _flag_25c_if_needed(temp_flags, prop_name="density_g_mL_25C", prop_value=density_g_ml, temp_status=dens_ts)
    _flag_25c_if_needed(
        temp_flags,
        prop_name="water_solubility_mg_L_25C",
        prop_value=water_solubility_mg_l,
        temp_status=sol_ts,
    )

    if temp_flags:
        _append_warning(warnings, "25C-check: " + " | ".join(temp_flags))

    needs_review = bool(warnings)
    warnings_out = " ; ".join(warnings) if warnings else None

    # --- Source summarization ---
    source_primary, source_secondary = _summarize_sources(wide_row, logp_source_col)

    # --- Henry (Sander native units) ---
    # Wide input expected keys:
    #   experimental_henry_constant_mol_m3_pa (numeric; mol m^-3 Pa^-1)
    #   source_henry_constant (verbose source string)
    henry = as_float(wide_row.get("experimental_henry_constant_mol_m3_pa"))
    log_henry = log10_or_none(henry)
    source_henry_constant = wide_row.get("source_henry_constant")

    # --- HSP (Hansen) measured + computed (sqrt(MPa)); all-or-none enforced ---
    exp_d = as_float(wide_row.get("experimental_hsp_delta_d_mpa05"))
    exp_p = as_float(wide_row.get("experimental_hsp_delta_p_mpa05"))
    exp_h = as_float(wide_row.get("experimental_hsp_delta_h_mpa05"))
    if (exp_d is None) or (exp_p is None) or (exp_h is None):
        if any(v is not None for v in (exp_d, exp_p, exp_h)):
            _append_warning(warnings, "HSP measured incomplete (all-or-none enforced)")
        exp_d = exp_p = exp_h = None
        source_hsp = None
    else:
        source_hsp = wide_row.get("source_hsp")

    comp_d = as_float(wide_row.get("computed_hsp_delta_d_mpa05"))
    comp_p = as_float(wide_row.get("computed_hsp_delta_p_mpa05"))
    comp_h = as_float(wide_row.get("computed_hsp_delta_h_mpa05"))
    if (comp_d is None) or (comp_p is None) or (comp_h is None):
        if any(v is not None for v in (comp_d, comp_p, comp_h)):
            _append_warning(warnings, "HSP computed incomplete (all-or-none enforced)")
        comp_d = comp_p = comp_h = None
        source_hsp_computed = None
    else:
        source_hsp_computed = wide_row.get("source_hsp_computed")

    # --- Not present in current pipeline output (keep None) ---
    physical_state_25c = None
    is_volatile = None
    confidence_score = None

    timestamp_updated = wide_row.get("timestamp")

    return {
        "inchi_key": inchi_key,
        "cas_number": cas_number,
        "smiles": smiles,
        "name_preferred": name_preferred,
        "molecular_weight_g_mol": mw,
        "logP_octanol_water": logp,
        "topological_polar_surface_area_A2": tpsa,
        "num_heavy_atoms": num_heavy_atoms,
        "vapor_pressure_Pa_25C": vapor_pressure_pa,
        "log_vapor_pressure_Pa_25C": log_vapor_pressure,
        "henry_constant_mol_m3_Pa_25C": henry,
        "log_henry_constant_mol_m3_Pa_25C": log_henry,
        "source_henry_constant": source_henry_constant,
        "boiling_point_C": boiling_point_c,
        "melting_point_C": melting_point_c,
        "water_solubility_mg_L_25C": water_solubility_mg_l,
        "log_water_solubility_mg_L_25C": log_water_solubility,
        "density_g_mL_25C": density_g_ml,
        "experimental_hsp_delta_d_mpa05": exp_d,
        "experimental_hsp_delta_p_mpa05": exp_p,
        "experimental_hsp_delta_h_mpa05": exp_h,
        "source_hsp": source_hsp,
        "computed_hsp_delta_d_mpa05": comp_d,
        "computed_hsp_delta_p_mpa05": comp_p,
        "computed_hsp_delta_h_mpa05": comp_h,
        "source_hsp_computed": source_hsp_computed,
        "physical_state_25C": physical_state_25c,
        "is_volatile": is_volatile,
        "needs_review": needs_review,
        "source_primary": source_primary,
        "source_secondary": source_secondary,
        "confidence_score": confidence_score,
        "warnings": warnings_out,
        "timestamp_updated": timestamp_updated,
    }