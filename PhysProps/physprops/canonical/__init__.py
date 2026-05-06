# physprops/canonical/__init__.py
from .units import (
    is_null,
    as_float,
    parse_value_unit,
    norm_unit,
    log10_or_none,
    pressure_to_pa,
    temperature_to_c,
    density_to_g_ml,
    solubility_to_mg_l,
)

from .mapper import build_canonical_row

# builder.py may not exist yet in your folder at the moment you paste this.
# If it exists, this import will work; otherwise, comment it until you add builder.py.
try:
    from .builder import build_canonical_dataframe
except Exception:  # pragma: no cover
    build_canonical_dataframe = None  # type: ignore

__all__ = [
    # units
    "is_null",
    "as_float",
    "parse_value_unit",
    "norm_unit",
    "log10_or_none",
    "pressure_to_pa",
    "temperature_to_c",
    "density_to_g_ml",
    "solubility_to_mg_l",
    # mapping/build
    "build_canonical_row",
    "build_canonical_dataframe",
]