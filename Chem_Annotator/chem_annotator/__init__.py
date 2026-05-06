"""
Public API for the chem_annotator package.
"""

# Import the core aggregator function (fixes typo smil → smiles)
from .aggregator import features_for_smiles

# Re-export alcohol utilities from their real module
from .features.alcohols import classify_and_count_alcohols, audit_alcohol_sites

# Re-export constants as before
from .chem_patterns import (
    EXCLUDE_ALPHA_HYDROXY_CARBONYLS,
    EXCLUDE_ENOLS,
    TRACK_EXCLUDED_IN_AUDIT,
)

# Public API
__all__ = [
    "features_for_smiles",
    "classify_and_count_alcohols",
    "audit_alcohol_sites",
    "EXCLUDE_ALPHA_HYDROXY_CARBONYLS",
    "EXCLUDE_ENOLS",
    "TRACK_EXCLUDED_IN_AUDIT",
]