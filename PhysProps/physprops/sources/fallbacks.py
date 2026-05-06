"""
Heuristic fallback estimators for physical properties.

These fallbacks are used ONLY when no experimental PubChem data is available.
They populate ONLY computed_* fields and set source_* = "fallback" so the
final merging step can pick experimental > computed > none.

All heuristics are intentionally simple and transparent.
"""

import logging
from typing import Dict, Any, List, Optional
import math

logger = logging.getLogger(__name__)


# ------------------------------------------------------------
# Simple heuristics
# ------------------------------------------------------------

def estimate_density_g_ml(mw: float, clogp: float) -> Optional[float]:
    """Very crude heuristic density estimate."""
    if mw is None or clogp is None:
        return None

    if clogp > 3:
        density = 0.80
    elif clogp > 1:
        density = 0.95
    else:
        density = 1.15

    density *= (1 + (mw - 100) / 1500)
    return round(density, 3)


def estimate_vapor_pressure_pa(bp_c: float) -> Optional[float]:
    """Very crude Antoine-like vapor pressure estimate."""
    if bp_c is None:
        return None

    t_k = bp_c + 273.15

    A = 8.0
    B = 2000.0
    C = -50.0

    try:
        log10_p = A - B / (t_k + C)
        p = 10 ** log10_p
        return round(p, 2)
    except Exception as e:
        logger.warning(f"Vapor pressure heuristic failed: {e}")
        return None


def estimate_water_solubility_mg_l(clogp: float) -> Optional[float]:
    """Extremely crude solubility heuristic."""
    if clogp is None:
        return None

    if clogp < 0:
        return 100000.0
    elif clogp < 1:
        return 10000.0
    elif clogp < 3:
        return 1000.0
    elif clogp < 5:
        return 100.0
    else:
        return 1.0


def estimate_boiling_point_c(mw: float, ring_count: int) -> Optional[float]:
    """Heuristic boiling point estimate."""
    if mw is None:
        return None

    return round(0.6 * mw + 25 * (ring_count or 0), 1)


# ------------------------------------------------------------
# Apply fallbacks
# ------------------------------------------------------------

def apply_fallbacks(flat_results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fills missing computed_* fields using fallback heuristics.

    The function:
      - ONLY writes to computed_* fields
      - NEVER touches experimental_* fields
      - Sets source_* = "fallback" for those fields

    Parameters
    ----------
    flat_results : dict
        The already-merged result dictionary (experimental + computed from RDKit).

    Returns
    -------
    dict
        Updated dictionary with fallback-computed fields.
    """

    warnings = flat_results.setdefault("warnings", [])

    # Shortcuts
    mw = flat_results.get("computed_mw") or flat_results.get("experimental_mw")
    clogp = flat_results.get("computed_clogp") or flat_results.get("experimental_logp")
    ring_count = flat_results.get("computed_ring_count")

    # ------------------------------------------------------------
    # Boiling point
    # ------------------------------------------------------------
    if flat_results.get("computed_boiling_point_c") is None:
        est = estimate_boiling_point_c(mw, ring_count)
        if est is not None:
            flat_results["computed_boiling_point_c"] = est
            flat_results["source_boiling_point_c"] = "fallback"
            warnings.append("Boiling point estimated via fallback heuristic.")

    # ------------------------------------------------------------
    # Vapor pressure
    # ------------------------------------------------------------
    if flat_results.get("computed_vapor_pressure_pa") is None:
        # Prefer experimental BP if present because fallback VP depends on BP
        bp = (
            flat_results.get("experimental_boiling_point_c") 
            or flat_results.get("computed_boiling_point_c")
        )
        est = estimate_vapor_pressure_pa(bp)
        if est is not None:
            flat_results["computed_vapor_pressure_pa"] = est
            flat_results["source_vapor_pressure_pa"] = "fallback"
            warnings.append("Vapor pressure estimated via fallback heuristic.")

    # ------------------------------------------------------------
    # Density
    # ------------------------------------------------------------
    if flat_results.get("computed_density_g_ml") is None:
        est = estimate_density_g_ml(mw, clogp)
        if est is not None:
            flat_results["computed_density_g_ml"] = est
            flat_results["source_density_g_ml"] = "fallback"
            warnings.append("Density estimated via fallback heuristic.")

    # ------------------------------------------------------------
    # Water solubility
    # ------------------------------------------------------------
    if flat_results.get("computed_water_solubility_mg_l") is None:
        est = estimate_water_solubility_mg_l(clogp)
        if est is not None:
            flat_results["computed_water_solubility_mg_l"] = est
            flat_results["source_water_solubility_mg_l"] = "fallback"
            warnings.append("Water solubility estimated via fallback heuristic.")

    return flat_results