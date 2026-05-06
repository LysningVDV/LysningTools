# physprops/canonical/units.py
from __future__ import annotations

import math
import re
from typing import Any, Optional, Tuple, List


_NUM_UNIT_RE = re.compile(
    r"^\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*([^\d\s].*)?\s*$"
)


def is_null(x: Any) -> bool:
    """True for None, NaN, or empty/whitespace strings."""
    return (
        x is None
        or (isinstance(x, float) and math.isnan(x))
        or (isinstance(x, str) and x.strip() == "")
    )


def as_float(x: Any) -> Optional[float]:
    """Parse x into float; returns None if missing/unparseable."""
    if is_null(x):
        return None
    try:
        return float(x)
    except Exception:
        return None


def norm_unit(u: str) -> str:
    """
    Normalize unit strings:
      - lower-case
      - remove spaces and degree symbol
      - normalize micro symbols to 'u'
    """
    return (
        u.lower()
        .replace(" ", "")
        .replace("°", "")
        .replace("μ", "u")
        .replace("µ", "u")
    )


def parse_value_unit(x: Any) -> Tuple[Optional[float], Optional[str], bool]:
    """
    Returns (value_float, unit_str_or_None, has_explicit_unit_bool)

    Supported input forms:
      - numeric:              1.23                 -> (1.23, None, False)
      - string:               "1.23 bar"           -> (1.23, "bar", True)
      - dict:                 {"value":1.23,"unit":"bar"} -> (1.23,"bar",True)
      - tuple/list:           (1.23, "bar")        -> (1.23, "bar", True)

    If string isn't parseable as "<number> <unit>", returns (None, None, False).
    """
    if is_null(x):
        return None, None, False

    if isinstance(x, dict) and "value" in x:
        v = as_float(x.get("value"))
        u = x.get("unit")
        u = str(u).strip() if not is_null(u) else None
        return v, u, u is not None

    if isinstance(x, (tuple, list)) and len(x) == 2:
        v = as_float(x[0])
        u = str(x[1]).strip() if not is_null(x[1]) else None
        return v, u, u is not None

    if isinstance(x, (int, float)) and not (isinstance(x, float) and math.isnan(x)):
        return float(x), None, False

    if isinstance(x, str):
        m = _NUM_UNIT_RE.match(x)
        if not m:
            return None, None, False
        v = as_float(m.group(1))
        u = m.group(2)
        u = u.strip() if u else None
        return v, u, u is not None

    return None, None, False


def log10_or_none(x: Any) -> Optional[float]:
    """
    Deterministic base-10 log:
      - returns None if x is missing or <= 0
    """
    v = as_float(x)
    if v is None or v <= 0:
        return None
    return math.log10(v)


def pressure_to_pa(x: Any, warnings: Optional[List[str]] = None) -> Optional[float]:
    """
    Convert explicit-unit pressure to Pa.
    If no explicit unit is present, returns numeric as-is (assumes already Pa).

    Supported units: Pa, kPa, MPa, bar, mbar, atm, torr, mmHg.
    """
    v, u, has_u = parse_value_unit(x)
    if v is None:
        return None

    if not has_u:
        return v

    uu = norm_unit(u)
    conv = {
        "pa": 1.0,
        "kpa": 1e3,
        "mpa": 1e6,
        "bar": 1e5,
        "mbar": 1e2,
        "atm": 101325.0,
        "torr": 133.322368,
        "mmhg": 133.322368,
    }

    if uu not in conv:
        if warnings is not None:
            warnings.append(f"Unit conversion: unsupported pressure unit '{u}' (kept raw numeric)")
        return v

    return v * conv[uu]


def temperature_to_c(x: Any, warnings: Optional[List[str]] = None) -> Optional[float]:
    """
    Convert explicit-unit temperature to °C.
    If no explicit unit is present, returns numeric as-is (assumes already °C).

    Supported units: C/°C, K, F/°F.
    """
    v, u, has_u = parse_value_unit(x)
    if v is None:
        return None

    if not has_u:
        return v

    uu = norm_unit(u)

    if uu in ("c", "degc"):
        return v
    if uu in ("k", "degk"):
        return v - 273.15
    if uu in ("f", "degf"):
        return (v - 32.0) * 5.0 / 9.0

    if warnings is not None:
        warnings.append(f"Unit conversion: unsupported temperature unit '{u}' (kept raw numeric)")
    return v


def density_to_g_ml(x: Any, warnings: Optional[List[str]] = None) -> Optional[float]:
    """
    Convert explicit-unit density to g/mL.
    If no explicit unit is present, returns numeric as-is (assumes already g/mL).

    Supported units: g/mL, g/cm3, g/cc, kg/m3, mg/mL.
    """
    v, u, has_u = parse_value_unit(x)
    if v is None:
        return None

    if not has_u:
        return v

    uu = norm_unit(u)
    conv = {
        "g/ml": 1.0,
        "g/cm3": 1.0,
        "g/cc": 1.0,
        "kg/m3": 0.001,   # 1 kg/m^3 = 0.001 g/mL
        "mg/ml": 0.001,   # 1 mg/mL = 0.001 g/mL
    }

    if uu not in conv:
        if warnings is not None:
            warnings.append(f"Unit conversion: unsupported density unit '{u}' (kept raw numeric)")
        return v

    return v * conv[uu]


def solubility_to_mg_l(
    x: Any,
    *,
    mw_g_mol: Optional[float] = None,
    warnings: Optional[List[str]] = None,
    assume_ppm_mg_l: bool = True,
) -> Optional[float]:
    """
    Convert explicit-unit water solubility to mg/L.
    If no explicit unit is present, returns numeric as-is (assumes already mg/L).

    Supported mass units:
      - mg/L, g/L, mg/mL, ug/mL, ng/mL, g/mL

    Supported molar units (requires MW):
      - mol/L (M), mM, uM

    ppm handling (Option 1):
      - Treat ppm as mg/L (aqueous approximation) AND warn.

    If unit is unsupported/ambiguous:
      - Warn and keep numeric value unchanged.
    """
    v, u, has_u = parse_value_unit(x)
    if v is None:
        return None

    if not has_u:
        return v

    uu = norm_unit(u)

    mass_conv = {
        "mg/l": 1.0,
        "g/l": 1000.0,
        "mg/ml": 1000.0,      # 1 mg/mL = 1000 mg/L
        "ug/ml": 1.0,         # 1 ug/mL = 1 mg/L
        "ng/ml": 0.001,       # 1 ng/mL = 0.001 mg/L
        "g/ml": 1_000_000.0,  # 1 g/mL = 1,000,000 mg/L
    }

    if uu in mass_conv:
        return v * mass_conv[uu]

    if uu == "ppm":
        if warnings is not None:
            warnings.append("Unit conversion: treated ppm as mg/L (aqueous approximation)")
        return v if assume_ppm_mg_l else v

    def _need_mw() -> Optional[float]:
        if mw_g_mol is None:
            if warnings is not None:
                warnings.append(f"Unit conversion: solubility '{u}' requires MW (missing); kept raw numeric")
            return None
        return float(mw_g_mol)

    # molar units -> mg/L = (mol/L) * (g/mol) * 1000 mg/g
    if uu in ("mol/l", "m", "molar"):
        mw = _need_mw()
        if mw is None:
            return v
        return v * mw * 1000.0

    if uu in ("mmol/l", "mmolar", "mm"):
        mw = _need_mw()
        if mw is None:
            return v
        return (v / 1000.0) * mw * 1000.0

    if uu in ("umol/l", "umolar", "um"):
        mw = _need_mw()
        if mw is None:
            return v
        return (v / 1_000_000.0) * mw * 1000.0

    if warnings is not None:
        warnings.append(f"Unit conversion: unsupported solubility unit '{u}' (kept raw numeric)")
    return v