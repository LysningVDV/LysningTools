"""
Name-resolution subpackage.

Provides:
- name normalization
- PubChem name → CID lookup
- CID → structure/property extraction
- multi-candidate ranking
- high-level resolver interface
"""

from .resolver import resolve_name