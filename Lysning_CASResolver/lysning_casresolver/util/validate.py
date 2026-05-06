import logging
import re

logger = logging.getLogger(__name__)

# Strict CAS format: A-BB-C where:
#   A: 1–7 digits
#   B: exactly 2 digits
#   C: check digit (0–9)
CAS_REGEX = re.compile(r"^\d{1,7}-\d{2}-\d$")


def normalize_cas(raw: str):
    """
    Normalize and clean a CAS number.

    Returns
    -------
    (normalized_cas, warning_string)

    Warning string describes any cleaning steps applied:
        "removed illegal characters"
        "added dashes"
        "repositioned dashes"
        "padded middle block"
        ...
    Multiple warnings are joined with "; ".

    Parameters
    ----------
    raw : str

    Returns
    -------
    tuple
        (normalized_cas, warning_string)

    Raises
    ------
    ValueError
        If the CAS number cannot be normalized at all.
    """
    if raw is None:
        raise ValueError("CAS string cannot be None.")

    original = str(raw)
    s = original.strip()
    warnings = []

    # Detect and remove illegal characters
    cleaned = re.sub(r"[^0-9-]", "", s)
    if cleaned != s:
        warnings.append("removed illegal characters")
        logger.debug("Removed illegal characters: '%s' -> '%s'", s, cleaned)
    s = cleaned

    # Case 1: Already contains dashes
    if "-" in s:
        parts = s.split("-")
        if len(parts) != 3:
            # Try to reconstruct if possible
            digits_only = re.sub(r"-", "", s)
            if not digits_only.isdigit() or len(digits_only) < 4:
                raise ValueError(f"CAS '{original}' has an invalid dash pattern.")

            # Rebuild from digits
            warnings.append("repositioned dashes")
            a = digits_only[:-3]
            b = digits_only[-3:-1]
            c = digits_only[-1]
            normalized = f"{int(a)}-{b}-{c}"

            # block B must be 2 digits
            if len(b) != 2:
                padded_b = b.zfill(2)
                normalized = f"{int(a)}-{padded_b}-{c}"
                warnings.append("padded middle block")
            return normalized, "; ".join(warnings)

        # Validate parts
        a, b, c = parts
        if not (a.isdigit() and b.isdigit() and c.isdigit()):
            raise ValueError(f"CAS '{original}' contains non-digit components.")

        # Normalize dash placement and zero-pad block B if needed
        normalized = f"{int(a)}-{b.zfill(2)}-{c}"
        if b != b.zfill(2):
            warnings.append("padded middle block")

        # No structural change? If not, mark general normalization
        if normalized != original:
            warnings.append("general normalization applied")

        return normalized, "; ".join(warnings)

    # Case 2: pure digits → reconstruct A-BB-C
    if s.isdigit():
        digits = s
        if len(digits) < 4:
            raise ValueError(f"CAS '{original}' is too short for reconstruction.")

        warnings.append("added dashes")
        a = digits[:-3]
        b = digits[-3:-1]
        c = digits[-1]

        normalized = f"{int(a)}-{b}-{c}"

        # block B must be exactly 2 digits
        if len(b) != 2:
            normalized = f"{int(a)}-{b.zfill(2)}-{c}"
            warnings.append("padded middle block")

        return normalized, "; ".join(warnings)

    raise ValueError(f"CAS '{original}' could not be normalized.")


def is_valid_cas(cas: str) -> bool:
    """
    Validate CAS format and checksum.

    Parameters
    ----------
    cas : str

    Returns
    -------
    bool
    """
    try:
        normalized, _ = normalize_cas(cas)
    except Exception:
        return False

    if not CAS_REGEX.match(normalized):
        return False

    a, b, c = normalized.split("-")
    check_digit = int(c)
    digits = a + b  # exclude check digit

    total = 0
    multiplier = 1
    for d in reversed(digits):
        total += int(d) * multiplier
        multiplier += 1

    return (total % 10) == check_digit


def validate_cas(cas: str) -> str:
    """
    Validate a CAS number and return the normalized version.

    Parameters
    ----------
    cas : str

    Returns
    -------
    str
        Normalized CAS

    Raises
    ------
    ValueError
        If invalid.
    """
    normalized, _ = normalize_cas(cas)

    if not is_valid_cas(normalized):
        raise ValueError(f"Invalid CAS number: '{cas}'")

    return normalized


def classify_mixture(cas: str) -> str:
    """
    Classify CAS number as single substance, polymer/mixture, fragrance mixture,
    or natural product/UVCB. Classification is applied **even if CAS is invalid**.

    Logic (based on first block):
        >=90000             → natural product / UVCB
        80000–89999         → fragrance / essential oil / mixture
        60000–69999         → polymer / complex mixture
        else                → single substance

    If CAS cannot be parsed at all, returns "unknown".

    Parameters
    ----------
    cas : str

    Returns
    -------
    str
        Mixture classification label.
    """
    try:
        normalized, _ = normalize_cas(cas)
    except Exception:
        logger.debug("CAS '%s' could not be normalized; mixture type unknown.", cas)
        return "unknown"

    try:
        a, _, _ = normalized.split("-")
        first_block = int(a)
    except Exception:
        logger.debug("CAS '%s' could not yield a numeric first block.", cas)
        return "unknown"

    # Classification rules
    if first_block >= 90000:
        return "natural product / UVCB"
    if 80000 <= first_block <= 89999:
        return "fragrance / essential oil / mixture"
    if 60000 <= first_block <= 69999:
        return "polymer / complex mixture"
    return "single substance"