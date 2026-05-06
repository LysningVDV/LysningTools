import logging
import unicodedata

logger = logging.getLogger(__name__)


def normalize_name(name: str) -> tuple[str, str]:
    """
    Normalize a chemical name for PubChem name-based resolution.

    Transformation steps:
      - strip leading/trailing whitespace
      - collapse multiple spaces to a single space
      - lowercase
      - remove accents (NFD unicode decomposition)
      - remove trailing punctuation (, ; . :)
      - ensure the result is ASCII-safe

    Parameters
    ----------
    name : str
        The user-provided name.

    Returns
    -------
    (normalized_name, warning_message)
        normalized_name : str
            The cleaned and ASCII-normalized name.
        warning_message : str
            "name normalization applied" if changes were made, else "".

    Notes
    -----
    This function is intentionally permissive and does not attempt to
    correct chemical syntax – it only performs linguistic normalization.
    """
    if name is None:
        return "", "empty input"

    original = str(name)

    # Step 1 — basic whitespace normalization
    cleaned = original.strip()
    cleaned = " ".join(cleaned.split())

    # Step 2 — lowercase
    cleaned = cleaned.lower()

    # Step 3 — strip accents via unicode decomposition
    nfkd = unicodedata.normalize("NFD", cleaned)
    ascii_clean = nfkd.encode("ascii", "ignore").decode("ascii")

    # Step 4 — remove trailing punctuation
    while ascii_clean and ascii_clean[-1] in ",.;:":
        ascii_clean = ascii_clean[:-1]

    # Step 5 — final whitespace cleanup
    ascii_clean = ascii_clean.strip()

    # Determine if changes occurred
    changed = (ascii_clean != original)

    if changed:
        logger.debug("Name normalization applied: '%s' -> '%s'", original, ascii_clean)
        warning = "name normalization applied"
    else:
        warning = ""

    return ascii_clean, warning