"""
Utility module for identifier and unit normalization.

Functions included:
- normalize_cas
- normalize_smiles
- normalize_inchi
- normalize_name
- strip_accents
- clean_whitespace
- normalize_pubchem_unit

This module validates and normalizes identifiers and transforms
PubChem-retrieved units into canonical forms for downstream processing.
"""

import re
import logging
import unicodedata

logger = logging.getLogger(__name__)


# ------------------------------------------------------------
# Accent / whitespace normalization
# ------------------------------------------------------------

def strip_accents(text: str) -> str:
    """
    Remove diacritical marks from a string.
    """
    if text is None:
        return None
    normalized = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def clean_whitespace(text: str) -> str:
    """
    Replace repeated whitespace with single spaces and strip ends.
    """
    if text is None:
        return None
    return re.sub(r"\s+", " ", text).strip()


# ------------------------------------------------------------
# CAS normalization
# ------------------------------------------------------------

def normalize_cas(cas: str) -> str:
    """
    Normalize CAS number formatting and validate checksum.

    Accepted format: NNNNNN-NN-N
    """
    if cas is None:
        return None

    cas = cas.strip()

    # Remove non-digit/hyphen characters
    cas = re.sub(r"[^0-9-]", "", cas)

    # If already matches canonical pattern, just validate checksum
    if not re.match(r"^\d{2,7}-\d{2}-\d$", cas):
        # Attempt to regroup digits
        digits = re.sub(r"-", "", cas)
        if len(digits) < 3:
            return None
        # Last digit is checksum, previous two digits are middle block, rest is first block
        cas = f"{digits[:-3]}-{digits[-3:-1]}-{digits[-1]}"

    if not _validate_cas_checksum(cas):
        logger.warning(f"CAS '{cas}' failed checksum validation.")
        return None

    return cas


def _validate_cas_checksum(cas: str) -> bool:
    """
    Validate CAS number checksum.
    """
    m = re.match(r"^(\d+)-(\d+)-(\d)$", cas)
    if not m:
        return False

    a, b, c = m.groups()
    digits = list(map(int, list(a + b)))

    # Reverse positional multipliers
    multipliers = list(range(1, len(digits) + 1))
    checksum = sum(d * m for d, m in zip(digits[::-1], multipliers))

    return (checksum % 10) == int(c)


# ------------------------------------------------------------
# SMILES normalization
# ------------------------------------------------------------

def normalize_smiles(smiles: str) -> str:
    """
    Normalize SMILES strings by trimming whitespace.
    (Canonicalization will be done in compute/rdkit.py)
    """
    if smiles is None:
        return None
    return smiles.strip()


# ------------------------------------------------------------
# InChI normalization
# ------------------------------------------------------------

def normalize_inchi(inchi: str) -> str:
    """
    Normalize InChI string formatting.
    """
    if inchi is None:
        return None
    inchi = inchi.strip()

    # Ensure correct prefix
    if not inchi.startswith("InChI="):
        if inchi.startswith("1S/") or inchi.startswith("1/"):
            inchi = "InChI=" + inchi

    return inchi


# ------------------------------------------------------------
# Name normalization
# ------------------------------------------------------------

def normalize_name(name: str) -> str:
    """
    Normalize chemical names:
    - Strip accents
    - Lowercase
    - Clean whitespace
    """
    if name is None:
        return None

    name = strip_accents(name)
    name = clean_whitespace(name)
    name = name.lower()

    return name


# ------------------------------------------------------------
# PubChem unit normalization
# ------------------------------------------------------------

def normalize_pubchem_unit(value: float, unit: str, warnings: list):
    """
    Normalize PubChem property units into canonical forms.

    Returns float or None.

    Supported:
    - Kelvin → Celsius
    - Fahrenheit → Celsius
    - atm, torr, mmHg, bar → Pascal (for vapor pressure)
    - Default: return value unchanged but warning added
    """

    if value is None:
        return None

    if unit is None:
        warnings.append("Missing unit for PubChem property; value kept raw.")
        return value

    u = unit.strip().lower()

    # ------------------------------------------
    # Temperature conversions
    # ------------------------------------------
    if u in ["k", "kelvin"]:
        return value - 273.15

    if u in ["c", "°c", "celsius"]:
        return value

    if u in ["f", "°f", "fahrenheit"]:
        return (value - 32.0) * 5.0 / 9.0

    # ------------------------------------------
    # Vapor pressure conversions → Pascal
    # ------------------------------------------
    if u in ["pa", "pascal", "pascals"]:
        return value

    if u in ["kpa"]:
        return value * 1000.0

    if u in ["mpa"]:
        return value * 1_000_000.0

    if u in ["bar"]:
        return value * 100_000.0

    if u in ["mbar", "millibar"]:
        return value * 100.0

    if u in ["atm"]:
        return value * 101_325.0

    if u in ["torr", "mmhg"]:
        # 1 torr ≈ 133.322 Pa
        return value * 133.322

    # Unknown unit
    warnings.append(f"Unknown unit '{unit}' from PubChem; value kept unconverted.")
    return value

# ------------------------------------------------------------
# Generic null / numeric helpers (used across canonical mapping)
# ------------------------------------------------------------

import math
from typing import Any, Optional

# ------------------------------------------------------------
# Generic null / numeric helpers (used across canonical mapping)
# ------------------------------------------------------------


def is_null(x: Any) -> bool:
    """
    True if x should be treated as missing/blank.

    Rules:
    - None -> null
    - NaN (float) -> null
    - empty/whitespace-only strings -> null
    """
    if x is None:
        return True
    if isinstance(x, float) and math.isnan(x):
        return True
    if isinstance(x, str) and x.strip() == "":
        return True
    return False



def as_float(x: Any) -> Optional[float]:
    """
    Convert x to float if possible; return None if blank or not parseable.
    """
    if is_null(x):
        return None
    try:
        return float(x)
    except Exception:
        return None
