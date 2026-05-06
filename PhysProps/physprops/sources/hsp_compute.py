
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple, TYPE_CHECKING
import importlib


# -----------------------------------------------------------------------------
# Public data structure
# -----------------------------------------------------------------------------
@dataclass(frozen=True)
class HSPTripletMPA05:
    """
    Hansen solubility parameters in MPa^0.5 (sqrt(MPa)).
    """
    delta_d_mpa05: float
    delta_p_mpa05: float
    delta_h_mpa05: float


# -----------------------------------------------------------------------------
# Deterministic method policy (explicit; WDR_SCHRIER fallback last)
# -----------------------------------------------------------------------------
COMPUTED_METHOD_ORDER = [
    "ALSHERI_HANSEN",
    "MANUEL_RUBEN_2022",
    "HSPIPY",
    "WDR_SCHRIER",  # fallback (as agreed)
]
# chemicals.solubility returns Hansen δ parameters in [Pa^0.5] and supports explicit methods. 


# Pylance friendliness: optional import for type checking only
if TYPE_CHECKING:
    pass  # type: ignore


PA05_TO_MPA05 = 1.0 / 1000.0  # Pa^0.5 -> MPa^0.5 (sqrt(Pa) / 1000 == sqrt(MPa))


def compute_hsp_triplet_from_chemicals(
    casrn: Optional[str],
) -> Tuple[Optional[HSPTripletMPA05], Optional[str], Optional[str]]:
    """
    Deterministic computed HSP from chemicals.solubility.

    Inputs:
      casrn: CAS Registry Number string (required; chemicals lookup is CAS-based). 

    Behavior:
      - Tries methods in COMPUTED_METHOD_ORDER (explicit; no auto-selection).
      - For each method, retrieves δD, δP, δH using the SAME method.
      - All-or-none: only returns triplet if all three are present for that method.
      - Converts units from Pa^0.5 to MPa^0.5 by dividing by 1000,
        because chemicals returns δ in [Pa^0.5] and we store/export as sqrt(MPa). 

    Returns:
      (triplet_mpa05, source_string, warning_token)
    """
    if not casrn or not str(casrn).strip():
        return None, None, "HSP computed unavailable (no CAS)"

    casrn = str(casrn).strip()

    # Optional dependency import at runtime (safe)
    try:
        solubility = importlib.import_module("chemicals.solubility")
        hansen_delta_d = getattr(solubility, "hansen_delta_d")
        hansen_delta_p = getattr(solubility, "hansen_delta_p")
        hansen_delta_h = getattr(solubility, "hansen_delta_h")
    except Exception:
        return None, None, "HSP computed unavailable (chemicals not installed)"

    last_incomplete = None

    for method in COMPUTED_METHOD_ORDER:
        d = hansen_delta_d(casrn, method=method)
        p = hansen_delta_p(casrn, method=method)
        h = hansen_delta_h(casrn, method=method)

        if (d is not None) and (p is not None) and (h is not None):
            # Convert Pa^0.5 -> MPa^0.5
            d_mpa05 = float(d) * PA05_TO_MPA05
            p_mpa05 = float(p) * PA05_TO_MPA05
            h_mpa05 = float(h) * PA05_TO_MPA05

            triplet = HSPTripletMPA05(d_mpa05, p_mpa05, h_mpa05)
            src = (
                f"chemicals.solubility hansen_delta_* method={method}; "
                "basis=CASRN; "
                "units=Pa^0.5->MPa^0.5 (/1000)"
            )
            return triplet, src, None

        last_incomplete = f"HSP computed incomplete for method={method}; tried next"

    # No method succeeded
    warn = last_incomplete or f"HSP computed unavailable for CAS={casrn}"
    return None, None, warn
