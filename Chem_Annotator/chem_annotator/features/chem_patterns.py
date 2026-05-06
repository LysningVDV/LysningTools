"""
Shim so that feature modules can use:
    from .chem_patterns import ...
Even though the real definitions live in the parent package.

This avoids editing every feature module.
"""

from ..chem_patterns import *  # forward everything

# Optional: declare names explicitly
__all__ = [
    "PATTS",
    "ESTER_PATT",
    "EXCLUDE_ALPHA_HYDROXY_CARBONYLS",
    "EXCLUDE_ENOLS",
    "TRACK_EXCLUDED_IN_AUDIT",
]