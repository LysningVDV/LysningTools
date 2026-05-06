import json
import os
import threading
import logging
from datetime import datetime
import pandas as pd

logger = logging.getLogger(__name__)

# Default JSON cache location in user's home directory
DEFAULT_CACHE_DIR = os.path.join(os.path.expanduser("~"), ".lysning_casresolver")
DEFAULT_CACHE_PATH = os.path.join(DEFAULT_CACHE_DIR, "cache.json")

# Thread safety for JSON cache operations
_cache_lock = threading.Lock()
_json_cache = None  # Lazy-loaded in-memory cache


# ----------------------------------------------------------------------
# JSON CACHE FUNCTIONS
# ----------------------------------------------------------------------

def _ensure_cache_directory(path: str = None):
    """
    Ensure the cache directory exists. Creates directories if needed.
    """
    if path is None:
        path = DEFAULT_CACHE_PATH

    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    logger.debug("Ensured cache directory exists: %s", directory)


def load_json_cache(path: str = None):
    """
    Lazily load JSON cache into memory.

    Returns the internal cache dictionary.

    Parameters
    ----------
    path : str, optional

    Returns
    -------
    dict
    """
    global _json_cache

    if path is None:
        path = DEFAULT_CACHE_PATH

    with _cache_lock:
        if _json_cache is not None:
            return _json_cache

        _ensure_cache_directory(path)

        if not os.path.exists(path):
            logger.debug("JSON cache file does not exist; starting empty cache.")
            _json_cache = {}
            return _json_cache

        try:
            with open(path, "r", encoding="utf-8") as f:
                _json_cache = json.load(f)
                logger.debug("Loaded JSON cache from %s", path)
        except Exception as exc:
            logger.error("Failed to load JSON cache from %s: %s", path, exc)
            _json_cache = {}

        return _json_cache


def save_json_cache(path: str = None):
    """
    Save the internal JSON cache to disk.

    Parameters
    ----------
    path : str, optional
    """
    global _json_cache

    if path is None:
        path = DEFAULT_CACHE_PATH

    with _cache_lock:
        if _json_cache is None:
            logger.debug("No JSON cache in memory; nothing to save.")
            return

        _ensure_cache_directory(path)

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(_json_cache, f, indent=2)
                logger.debug("Saved JSON cache to %s", path)
        except Exception as exc:
            logger.error("Error saving JSON cache to %s: %s", path, exc)
            raise


def get_cached(key: str, path: str = None):
    """
    Retrieve an entry from the JSON cache by key (CAS or name).

    Parameters
    ----------
    key : str
    path : str, optional

    Returns
    -------
    dict or None
    """
    cache = load_json_cache(path)
    entry = cache.get(key)
    if entry:
        logger.debug("Cache hit for key '%s'.", key)
    else:
        logger.debug("Cache miss for key '%s'.", key)
    return entry


def set_cached(key: str, data: dict, path: str = None):
    """
    Store a resolved entry into the JSON cache.

    Automatically adds timestamp if not provided.

    Parameters
    ----------
    key : str
    data : dict
    path : str, optional
    """
    cache = load_json_cache(path)

    if "timestamp" not in data:
        data["timestamp"] = datetime.utcnow().isoformat() + "Z"

    cache[key] = data
    logger.debug("Cached entry under key '%s': %s", key, data)
    save_json_cache(path)


# ----------------------------------------------------------------------
# EXCEL CACHE FUNCTIONS
# ----------------------------------------------------------------------

EXPECTED_EXCEL_COLUMNS = [
    "input",
    "cas",
    "smiles",
    "inchi",
    "inchikey",
    "mw",
    "source",
    "timestamp",
    "mixture_type",
    "warning"
]


def load_excel_cache(path: str) -> pd.DataFrame:
    """
    Load an Excel cache file into a pandas DataFrame.

    Raises error if file does not exist.

    Parameters
    ----------
    path : str

    Returns
    -------
    pandas.DataFrame
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Excel cache file not found: {path}")

    df = pd.read_excel(path, dtype=str)

    # Ensure expected columns exist (missing ones get filled)
    for col in EXPECTED_EXCEL_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    # Standardize column order
    df = df[EXPECTED_EXCEL_COLUMNS]

    logger.debug("Loaded Excel cache from %s with %d rows.", path, len(df))
    return df


def save_excel_cache(df: pd.DataFrame, path: str):
    """
    Save the DataFrame to an Excel file with proper column ordering.

    Parameters
    ----------
    df : DataFrame
    path : str
    """
    # Standardize order
    for col in EXPECTED_EXCEL_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    df = df[EXPECTED_EXCEL_COLUMNS]

    df.to_excel(path, index=False)
    logger.debug("Saved Excel cache to %s with %d rows.", path, len(df))


def merge_with_excel_cache(df_new: pd.DataFrame, excel_path: str) -> pd.DataFrame:
    """
    Merge new resolver results into an existing Excel cache.
    Deduplicates by CAS or input.

    Parameters
    ----------
    df_new : DataFrame
    excel_path : str

    Returns
    -------
    DataFrame
    """
    if os.path.exists(excel_path):
        df_existing = load_excel_cache(excel_path)
    else:
        raise FileNotFoundError(f"Excel cache file not found: {excel_path}")

    # Combine
    df_combined = pd.concat([df_existing, df_new], ignore_index=True)

    # Deduplicate:
    # First prioritizing CAS when available, falling back to input
    df_combined["dedupe_key"] = df_combined["cas"].fillna("").replace("", df_combined["input"])
    df_combined = df_combined.drop_duplicates("dedupe_key").drop(columns=["dedupe_key"])

    logger.debug(
        "Merged new data into Excel cache: %d new rows, total %d rows.",
        len(df_new),
        len(df_combined)
    )

    return df_combined