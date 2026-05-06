import logging
import re
from rdkit import Chem

logger = logging.getLogger(__name__)

# ===============================================================
# CAS NORMALIZATION & VALIDATION
# ===============================================================

# Strict CAS format: A-BB-C where A=1–7 digits, B=2 digits, C=check digit
CAS_REGEX = re.compile(r"^\d{1,7}-\d{2}-\d$")


def normalize_cas(raw: str):
    """
    Normalize and clean a CAS number.
    Returns (normalized_cas, warnings_string).
    """

    if raw is None:
        raise ValueError("CAS string cannot be None.")

    original = str(raw)
    s = original.strip()
    warnings = []

    # Remove illegal characters
    cleaned = re.sub(r"[^0-9-]", "", s)
    if cleaned != s:
        warnings.append("removed illegal characters")
        logger.debug("Removed illegal characters: '%s' -> '%s'", s, cleaned)
    s = cleaned

    # Case 1: Already contains dashes
    if "-" in s:
        parts = s.split("-")
        if len(parts) != 3:
            # Reconstruct from digits if possible
            digits_only = re.sub(r"-", "", s)
            if not digits_only.isdigit() or len(digits_only) < 4:
                raise ValueError(f"CAS '{original}' has an invalid dash pattern.")

            warnings.append("repositioned dashes")
            a = digits_only[:-3]
            b = digits_only[-3:-1]
            c = digits_only[-1]
            normalized = f"{int(a)}-{b}-{c}"

            if len(b) != 2:
                normalized = f"{int(a)}-{b.zfill(2)}-{c}"
                warnings.append("padded middle block")

            return normalized, "; ".join(warnings)

        # Validate normal dashed patterns
        a, b, c = parts
        if not (a.isdigit() and b.isdigit() and c.isdigit()):
            raise ValueError(f"CAS '{original}' contains non-digit components.")

        normalized = f"{int(a)}-{b.zfill(2)}-{c}"
        if b != b.zfill(2):
            warnings.append("padded middle block")

        if normalized != original:
            warnings.append("general normalization applied")

        return normalized, "; ".join(warnings)

    # Case 2: pure digits
    if s.isdigit():
        digits = s
        if len(digits) < 4:
            raise ValueError(f"CAS '{original}' is too short.")

        warnings.append("added dashes")
        a = digits[:-3]
        b = digits[-3:-1]
        c = digits[-1]

        normalized = f"{int(a)}-{b}-{c}"

        if len(b) != 2:
            normalized = f"{int(a)}-{b.zfill(2)}-{c}"
            warnings.append("padded middle block")

        return normalized, "; ".join(warnings)

    raise ValueError(f"CAS '{original}' could not be normalized.")


def is_valid_cas(cas: str) -> bool:
    """Validate CAS format + checksum."""
    try:
        normalized, _ = normalize_cas(cas)
    except Exception:
        return False

    if not CAS_REGEX.match(normalized):
        return False

    a, b, c = normalized.split("-")
    check_digit = int(c)
    digits = a + b

    total = 0
    multiplier = 1
    for d in reversed(digits):
        total += int(d) * multiplier
        multiplier += 1

    return (total % 10) == check_digit


def validate_cas(cas: str) -> str:
    """Return normalized CAS or raise."""
    normalized, _ = normalize_cas(cas)
    if not is_valid_cas(normalized):
        raise ValueError(f"Invalid CAS number: '{cas}'")
    return normalized


# ===============================================================
# RDKit FALLBACK: InChI → SMILES
# ===============================================================

def inchi_to_smiles(inchi: str) -> str:
    """Convert InChI to SMILES using RDKit, if possible."""
    if not inchi or not isinstance(inchi, str):
        return ""

    try:
        mol = Chem.MolFromInchi(inchi)
        if mol:
            smiles = Chem.MolToSmiles(mol)
            logger.debug("RDKit fallback: InChI -> SMILES: %s -> %s", inchi, smiles)
            return smiles
        else:
            logger.debug("RDKit: no molecule parsed from InChI: %s", inchi)
    except Exception as exc:
        logger.debug("RDKit fallback error for InChI '%s': %s", inchi, exc)

    return ""


# ===============================================================
# ENHANCED MIXTURE CLASSIFICATION (CAS + name + structure)
# ===============================================================

def classify_by_cas(cas: str) -> str | None:
    """Classification by CAS first block."""
    if not cas:
        return None

    try:
        first, _, _ = cas.split("-")
        block = int(first)
    except Exception:
        return None

    if block >= 90000:
        return "natural product / UVCB"
    if 80000 <= block <= 89999:
        return "fragrance mixture"
    if 60000 <= block <= 69999:
        return "polymer / complex mixture"

    return None


def classify_name_by_patterns(name: str) -> str | None:
    """Detect mixture type from naming conventions typical in fragrance/natural products."""
    if not name:
        return None

    n = name.lower()

    natural_keywords = [
        "ess", "ess.", "essential oil", "eo", "abs", "absolute",
        "extract", "ext", "he", "huile", "resinoid", "oleoresin",
        "infusion", "balsam", "tincture"
    ]
    if any(k in n for k in natural_keywords):
        return "natural product / UVCB"

    mixture_keywords = [
        "mix", "compound", "accord", "blend",
        "fragrance", "perfume", "aroma"
    ]
    if any(k in n for k in mixture_keywords):
        return "fragrance mixture"

    polymer_keywords = [
        "poly", "polymer", "copolymer", "oligomer", "resin"
    ]
    if any(k in n for k in polymer_keywords):
        return "polymer / complex mixture"

    return None


def classify_mixture_enhanced(name: str, cas: str, smiles: str | None = None) -> str:
    """
    Enhanced mixture classifier combining:
      - CAS-block rules
      - name-based patterns
      - structure-based detection
    """

    # 1. CAS rules
    cas_class = classify_by_cas(cas)
    if cas_class:
        return cas_class

    # 2. Name patterns
    name_class = classify_name_by_patterns(name)
    if name_class:
        return name_class

    # 3. Structural detection (multi-component SMILES)
    if smiles and "." in smiles:
        return "mixture (multi-component structure)"

    # Default
    return "single substance"