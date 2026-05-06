import logging
import pandas as pd
import os

logger = logging.getLogger(__name__)

# These are the canonical columns for resolver output
EXPECTED_OUTPUT_COLUMNS = [
    "original_name",
    "original_cas",
    "input",
    "cas",
    "smiles",
    "inchi",
    "inchikey",
    "mw",
    "source",
    "warning",
    "mixture_type",
    "timestamp"
]

# Columns that may appear in input files (flexible)
POSSIBLE_INPUT_COLUMNS = [
    "input",
    "cas",
    "name",
    "query",
    "identifier",
    "raw",
]


def read_input_excel(path: str) -> pd.DataFrame:
    """
    Load an input Excel file containing at least 'Name' and 'CAS' columns.
    """

    if not os.path.exists(path):
        raise FileNotFoundError(f"Input Excel file not found: {path}")

    try:
        df = pd.read_excel(path, dtype=str)
    except Exception as exc:
        logger.error("Failed to read Excel: %s", exc)
        raise

    # Normalize column names
    df.columns = (
        df.columns
            .str.replace("'", "", regex=False)
            .str.replace("\u00A0", " ", regex=False)
            .str.replace("\ufeff", "", regex=False)
            .str.strip()
    )

    # Ensure required columns exist
    if "Name" not in df.columns or "CAS" not in df.columns:
        raise ValueError(
            f"Input Excel must contain 'Name' and 'CAS' columns. "
            f"Found: {list(df.columns)}"
        )

    # Keep only Name and CAS (ignore extra)
    df = df[["Name", "CAS"]].copy()

    logger.debug("Loaded Excel '%s' with %d rows", path, len(df))
    return df

def write_output_excel(df: pd.DataFrame, path: str):
    """
    Save a resolved DataFrame to Excel with standardized columns.

    Missing columns are added empty.
    Extra columns are preserved unless incompatible.

    Parameters
    ----------
    df : DataFrame
    path : str
    """
    df_out = df.copy()

    # Ensure all standard columns exist
    for col in EXPECTED_OUTPUT_COLUMNS:
        if col not in df_out.columns:
            df_out[col] = ""

    # Reorder
    df_out = df_out[EXPECTED_OUTPUT_COLUMNS]

    try:
        df_out.to_excel(path, index=False)
        logger.debug("Wrote output Excel '%s' with %d rows", path, len(df_out))
    except Exception as exc:
        logger.error("Failed to write Excel '%s': %s", path, exc)
        raise