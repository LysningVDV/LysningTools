"""
Identifier detection and routing utilities.

Determines whether an input string is:
- CAS number
- SMILES
- InChI
- InChIKey
- Name (default)

This module performs heuristic classification with validation using regex.
Normalization of each identifier type is handled in util/normalize.py.
"""

import re
import logging
from .normalize import (
    normalize_cas,
    normalize_smiles,
    normalize_inchi,
    normalize_name
)

logger = logging.getLogger(__name__)


# ------------------------------------------------------------
# Regular expressions for identifier detection
# ------------------------------------------------------------

CAS_PATTERN = re.compile(r"^\d{2,7}-\d{2}-\d$")
INCHIKEY_PATTERN = re.compile(r"^[A-Z]{14}-[A-Z]{10}-[A-Z]$")
INCHI_PATTERN = re.compile(r"^InChI=1[AS]?/.*", re.IGNORECASE)

# SMILES is tricky; use exclusion & common character patterns
SMILES_CHARS = set("#%()+-./:=@[]\\0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")


# ------------------------------------------------------------
# Public API
# ------------------------------------------------------------

def detect_identifier_type(text: str) -> str:
    """
    Detect the identifier type of the input string.

    Returns one of:
        - 'cas'
        - 'inchikey'
        - 'inchi'
        - 'smiles'
        - 'name'

    Falls back to 'name' for ambiguous cases.
    """
    if text is None:
        return None

    raw = text.strip()
    if raw == "":
        return "name"

    # CAS detection
    if CAS_PATTERN.match(raw):
        if normalize_cas(raw) is not None:
            logger.debug(f"Detected CAS identifier: {raw}")
            return "cas"

    # InChIKey detection
    if INCHIKEY_PATTERN.match(raw):
        logger.debug(f"Detected InChIKey identifier: {raw}")
        return "inchikey"

    # InChI detection
    if raw.lower().startswith("inchi=") or INCHI_PATTERN.match(raw):
        logger.debug(f"Detected InChI identifier: {raw}")
        return "inchi"

    # SMILES detection:
    # - Must only contain allowed SMILES characters
    # - Must contain characters likely used in SMILES
    if _looks_like_smiles(raw):
        logger.debug(f"Detected SMILES: {raw}")
        return "smiles"

    # Default → name
    logger.debug(f"Falling back to chemical name: {raw}")
    return "name"


def normalize_identifier(text: str, id_type: str) -> str:
    """
    Normalize an identifier according to its detected type.

    Returns the cleaned & normalized identifier or None.
    """
    if text is None:
        return None

    if id_type == "cas":
        return normalize_cas(text)
    if id_type == "inchikey":
        return text.strip().upper()  # InChIKeys always uppercase
    if id_type == "inchi":
        return normalize_inchi(text)
    if id_type == "smiles":
        return normalize_smiles(text)
    if id_type == "name":
        return normalize_name(text)

    return text.strip()


# ------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------

def _looks_like_smiles(text: str) -> bool:
    """
    Heuristic detection of SMILES strings by character set
    and patterns unlikely in names.
    """
    # Reject if whitespace inside (makes SMILES invalid)
    if " " in text:
        return False

    # If many characters fall outside SMILES typical set → not SMILES
    for ch in text:
        if ch not in SMILES_CHARS:
            return False

    # Names rarely contain brackets or ring numbers
    if any(ch in text for ch in ""):
        return True

    # Check for bond symbols
    if any(sym in text for sym in ("=", "#", "@")):
        return True

    # Contains digits -> likely ring indices
    if any(ch.isdigit() for ch in text):
        return True

    # If none of the above: ambiguous → treat as name
    return False