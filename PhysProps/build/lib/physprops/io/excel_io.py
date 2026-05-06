"""
Excel input/output utilities for the physprops package.

Responsibilities:
- Load an Excel file and detect the column containing chemical identifiers
- Preserve original column order
- Append new flat output columns (experimental/computed/final/source)
- Save output Excel cleanly

No chemical logic is implemented here; this module only handles I/O
and DataFrame structure.
"""

import logging
from typing import Optional, List

import pandas as pd

logger = logging.getLogger(__name__)


# ------------------------------------------------------------
# Input column detection
# ------------------------------------------------------------

def detect_identifier_column(df: pd.DataFrame) -> Optional[str]:
    """
    Attempt to identify the input column that contains chemical identifiers.

    Strategy:
        - Look for common headers: "cas", "identifier", "id", "smiles", "structure", "name"
        - If no match: select the first column

    Returns:
        column name or None if DataFrame empty
    """

    if df.empty:
        return None

    # Common header candidates
    candidates = ["cas", "identifier", "id", "smiles", "inchi", "inchikey", "name"]

    lower_cols = {c.lower(): c for c in df.columns}

    for key in candidates:
        if key in lower_cols:
            logger.debug(f"Identifier column detected: {lower_cols[key]}")
            return lower_cols[key]

    # Default: first column
    first_col = df.columns[0]
    logger.debug(f"No identifier header detected; using first column '{first_col}'")
    return first_col


# ------------------------------------------------------------
# Excel reading
# ------------------------------------------------------------

def load_excel(path: str, sheet_name: Optional[str] = None) -> pd.DataFrame:
    """
    Load an Excel sheet into a pandas DataFrame with no header alterations.

    Parameters:
        path : Excel file path
        sheet_name : None = first sheet

    Returns:
        DataFrame
    """
    try:
        df = pd.read_excel(path, sheet_name=sheet_name)
        logger.info(f"Loaded Excel file: {path}")
        return df
    except Exception as e:
        logger.error(f"Failed to load Excel file '{path}': {e}")
        raise


# ------------------------------------------------------------
# Excel writing
# ------------------------------------------------------------

def save_excel(df: pd.DataFrame, path: str) -> None:
    """
    Save a DataFrame to Excel, preserving column order.

    Parameters:
        df : DataFrame to save
        path : Output file path
    """
    try:
        df.to_excel(path, index=False)
        logger.info(f"Saved Excel file: {path}")
    except Exception as e:
        logger.error(f"Failed to save Excel file '{path}': {e}")
        raise


# ------------------------------------------------------------
# Column ordering helper
# ------------------------------------------------------------

def order_result_columns(original_columns: List[str], result_columns: List[str]) -> List[str]:
    """
    Produce a final ordered column list:

        1. Original input columns (unchanged order)
        2. New result columns, grouped by property

    Input:
        original_columns : existing columns in the source DataFrame
        result_columns   : new columns to append

    Returns:
        combined ordered column list
    """
    return list(original_columns) + list(result_columns)


# ------------------------------------------------------------
# Core entry function used by main.py
# ------------------------------------------------------------

def integrate_results_into_dataframe(df: pd.DataFrame,
                                     result_records: List[dict],
                                     identifier_col: str) -> pd.DataFrame:
    """
    Integrate a list of result dicts (flat output records produced from main)
    into the original DataFrame.

    Parameters:
        df : original DataFrame
        result_records : list of dictionaries, one per input row
        identifier_col : name of the identifier column in df

    Returns:
        DataFrame with new columns appended
    """

    # Convert result_records to a DataFrame
    results_df = pd.DataFrame(result_records)

    # Identify new columns
    new_cols = [c for c in results_df.columns if c not in df.columns]

    # Merge by row order (no join needed — index alignment)
    merged = pd.concat([df.reset_index(drop=True), results_df[new_cols].reset_index(drop=True)], axis=1)

    # Build final ordering: original cols + new cols
    final_columns = order_result_columns(list(df.columns), new_cols)
    merged = merged[final_columns]

    logger.debug(f"Integrated {len(new_cols)} result columns into DataFrame.")

    return merged