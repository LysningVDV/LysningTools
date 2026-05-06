"""
Feature counter namespace.

Important:
Do NOT import the parent package's aggregator here — it causes a circular import.
Only import modules inside the features/ package.
"""

# Export alcohol functionality
from .alcohols import classify_and_count_alcohols, audit_alcohol_sites

__all__ = [
    "classify_and_count_alcohols",
    "audit_alcohol_sites",
    "features_for_smiles",
]


def features_for_smiles(smi: str):
    """
    Optional convenience wrapper:
    Lazy-import the parent aggregator to avoid circular imports.
    This works because the import happens *at call time*, not module import time.
    """
    from ..aggregator import features_for_smiles as _real
    return _real(smi)