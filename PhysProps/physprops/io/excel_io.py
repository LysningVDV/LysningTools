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
from physprops.canonical.builder import build_canonical_dataframe
from pathlib import Path

import numpy as np
from physprops.canonical.schema import CANONICAL_ORDER
from canonical_common.canonical_db import (
    write_xlsx_atomic,
)

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
    Load an Excel sheet into a pandas DataFrame.

    Behavior:
        sheet_name=None     -> load FIRST sheet (not dict-of-DataFrames)
        sheet_name="Sheet1" -> load that sheet

    Returns:
        DataFrame
    """
    df = pd.read_excel(path, sheet_name=sheet_name, engine="openpyxl")
    if isinstance(df, dict):
        # When sheet_name=None pandas can return dict; force first sheet
        first = next(iter(df.keys()))
        df = df[first]
    return df


# ------------------------------------------------------------
# Excel writing
# ------------------------------------------------------------



def save_excel(df: pd.DataFrame, path: str, sheet_name: str = "Sheet1") -> None:
    write_xlsx_atomic(df, path, sheet_name=sheet_name)


# ------------------------------------------------------------
# Column ordering logic
# ------------------------------------------------------------

def order_result_columns(original_columns: List[str], new_columns: List[str]) -> List[str]:
    """
    Deterministic ordering for output columns:
      - Preserve original input column order
      - Then append new result columns grouped as:
            experimental__*, computed__*, final__*, source__*, then *_temperature_c
      - Finally append any other columns not matching those patterns
    """
    def group_key(c: str) -> int:
        cl = c.lower()
        if cl.startswith("experimental_"):
            return 10
        if cl.startswith("computed_"):
            return 20
        if cl.startswith("final_"):
            return 30
        if cl.startswith("source_"):
            return 40
        if cl.endswith("_temperature_c"):
            return 50
        return 60

    ordered_new = sorted(new_columns, key=lambda c: (group_key(c), c))
    return list(original_columns) + ordered_new


# ------------------------------------------------------------
# Integrate results (wide output)
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


# ------------------------------------------------------------
# maintains database
# ------------------------------------------------------------

def update_canonical_database(
    wide_excel_path: str,
    canonical_db_path: str,
    audit_excel_path: str = None,
    sheet_name: str = None,
    strict_schema: bool = True,
):
    """
    Update (maintain) a persistent canonical database Excel file.

    Deterministic behavior:
    - Builds canonical_df from the provided wide Excel (current run).
    - If canonical_db_path exists, merges by inchi_key (field-wise):
        * new non-blank values overwrite old values
        * blank / missing new values do NOT erase existing values
    - Writes canonical_db_path atomically (tmp -> replace).
    - Optionally writes the current-run audit log (dedupe log) to audit_excel_path.

    Notes:
    - We treat empty strings / whitespace-only strings as missing (NaN) so they do not overwrite.
    - Output rows are sorted by inchi_key.
    - Output columns follow CANONICAL_ORDER, then any extra columns sorted.
    """

    def _blank_to_nan(df: pd.DataFrame) -> pd.DataFrame:
        """Convert empty/whitespace strings to NaN across object columns (deterministic)."""
        df = df.copy()
        obj_cols = df.select_dtypes(include=["object", "string"]).columns
        for c in obj_cols:
            df[c] = df[c].apply(lambda x: np.nan if isinstance(x, str) and x.strip() == "" else x)
        return df

    def _atomic_write_xlsx(df: pd.DataFrame, path: Path) -> None:
        """Write to temp file then replace target (best-effort atomic on Windows)."""
        tmp = path.with_suffix(path.suffix + ".tmp")
        df.to_excel(tmp, index=False, engine="openpyxl")
        tmp.replace(path)

    # ---------------------------
    # Load wide output
    # ---------------------------
    df_wide = pd.read_excel(wide_excel_path, sheet_name=sheet_name, engine="openpyxl")
    if isinstance(df_wide, dict):
        first = next(iter(df_wide.keys()))
        df_wide = df_wide[first]

    # ---------------------------
    # Build canonical from this run
    # ---------------------------
    canonical_new, audit_df = build_canonical_dataframe(df_wide, strict_schema=strict_schema)

    if "inchi_key" not in canonical_new.columns:
        raise ValueError(f"Canonical build missing required key 'inchi_key' from wide file: {wide_excel_path}")

    # Normalize key deterministically
    canonical_new = canonical_new.copy()
    canonical_new["inchi_key"] = canonical_new["inchi_key"].astype(str).str.strip()
    canonical_new = canonical_new[canonical_new["inchi_key"].notna() & (canonical_new["inchi_key"] != "")]

    canonical_new = _blank_to_nan(canonical_new)
    canonical_new = _harmonize_identifiers(canonical_new)
    db_path = Path(canonical_db_path)

    # ---------------------------
    # Load existing DB (if present)
    # ---------------------------
    if db_path.exists():
        canonical_old = pd.read_excel(db_path, engine="openpyxl")
        if "inchi_key" not in canonical_old.columns:
            raise ValueError(f"Existing canonical DB missing 'inchi_key' column: {canonical_db_path}")

        canonical_old = canonical_old.copy()
        canonical_old["inchi_key"] = canonical_old["inchi_key"].astype(str).str.strip()
        canonical_old = canonical_old[canonical_old["inchi_key"].notna() & (canonical_old["inchi_key"] != "")]
        canonical_old = _blank_to_nan(canonical_old)
        canonical_old = _harmonize_identifiers(canonical_old)
        old_idx = canonical_old.set_index("inchi_key", drop=False)
        new_idx = canonical_new.set_index("inchi_key", drop=False)

        # Deterministic column set: canonical order + extras sorted
        all_cols = [c for c in CANONICAL_ORDER if (c in old_idx.columns) or (c in new_idx.columns)]
        extras = sorted([c for c in set(old_idx.columns).union(set(new_idx.columns)) if c not in all_cols])
        all_cols = all_cols + extras

        for c in all_cols:
            if c not in old_idx.columns:
                old_idx[c] = np.nan
            if c not in new_idx.columns:
                new_idx[c] = np.nan

        if canonical_new["inchi_key"].duplicated().any():
            logger.warning("Duplicate inchi_key detected in new canonical data; keeping first occurrence deterministically.")
            canonical_new = canonical_new.drop_duplicates(subset=["inchi_key"])
                                                                  
        if canonical_old["inchi_key"].duplicated().any():
            logger.warning("Duplicate inchi_key detected in existing canonical DB; keeping first occurrence deterministically.")
            canonical_old = canonical_old.drop_duplicates(subset=["inchi_key"])


        old_idx = old_idx[all_cols]
        new_idx = new_idx[all_cols]

        # Merge rule: prefer new values, but fill missing from old
        merged_idx = new_idx.combine_first(old_idx)

        # Optional: preserve old timestamp_updated where nothing substantive changed
        if "timestamp_updated" in merged_idx.columns and "timestamp_updated" in old_idx.columns and "timestamp_updated" in new_idx.columns:
            compare_cols = [c for c in all_cols if c not in ("inchi_key", "timestamp_updated")]

            # Determine if new has any non-missing value that differs from old (row-wise)
            common_keys = new_idx.index.intersection(old_idx.index)
            if len(common_keys) > 0 and len(compare_cols) > 0:
                n = new_idx.loc[common_keys, compare_cols]
                o = old_idx.loc[common_keys, compare_cols]

                # changed if new value is notna and (old isna or new != old)
                changed = pd.DataFrame(False, index=common_keys, columns=compare_cols)
                for c in compare_cols:
                    nv = n[c]
                    ov = o[c]

                    # Compare positionally (avoid pandas index-alignment pitfalls)
                    diff = pd.Series(
                        nv.astype(str).to_numpy() != ov.astype(str).to_numpy(),
                        index=nv.index
                    )

                    changed[c] = nv.notna() & (ov.isna() | diff)

                changed_any = changed.any(axis=1)

                # Default: keep old timestamp where no changes
                merged_idx.loc[common_keys, "timestamp_updated"] = old_idx.loc[common_keys, "timestamp_updated"]
                # For changed rows: use new timestamp
                merged_idx.loc[common_keys[changed_any], "timestamp_updated"] = new_idx.loc[common_keys[changed_any], "timestamp_updated"]

        canonical_merged = merged_idx.reset_index(drop=True)

    else:
        # No prior DB: new canonical becomes the DB
        # Ensure deterministic column order
        present = set(canonical_new.columns)
        all_cols = [c for c in CANONICAL_ORDER if c in present] + sorted([c for c in present if c not in CANONICAL_ORDER])
        canonical_merged = canonical_new[all_cols].copy()

    # Deterministic row order
    canonical_merged = canonical_merged.sort_values("inchi_key").reset_index(drop=True)

    # Deterministic final column order (again, for safety)
    present = set(canonical_merged.columns)
    ordered_cols = [c for c in CANONICAL_ORDER if c in present] + sorted([c for c in present if c not in CANONICAL_ORDER])
    canonical_merged = canonical_merged[ordered_cols]

    # ---------------------------
    # Write updated DB atomically
    # ---------------------------
    _atomic_write_xlsx(canonical_merged, db_path)

    # ---------------------------
    # Write audit log (this run)
    # ---------------------------
    if audit_excel_path:
        audit_path = Path(audit_excel_path)
        _atomic_write_xlsx(audit_df, audit_path)

    return canonical_merged, audit_df

def update_canonical_database_from_df(
    canonical_new: pd.DataFrame,
    canonical_db_path: str,
    audit_excel_path: str = None,
    audit_df: pd.DataFrame = None,
):
    """
    Update (maintain) canonical database from an already-built dataframe.

    Key: inchi_key (required).
    Merge rule (field-wise):
      - new non-blank values overwrite old values
      - blank/NaN/empty/whitespace values in new do NOT overwrite old values

    Deterministic:
      - rows sorted by inchi_key
      - columns follow CANONICAL_ORDER then any extras sorted

    Audit:
      - if audit_excel_path and audit_df provided, overwrite audit workbook
    """

    def _blank_to_nan(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        # Pandas future-proof: handle object + string dtype explicitly
        obj_cols = df.select_dtypes(include=["object", "string"]).columns
        for c in obj_cols:
            df[c] = df[c].apply(lambda x: np.nan if isinstance(x, str) and x.strip() == "" else x)
        return df

    def _atomic_write_xlsx(df: pd.DataFrame, path: Path) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        df.to_excel(tmp, index=False, engine="openpyxl")
        tmp.replace(path)

    if "inchi_key" not in canonical_new.columns:
        raise ValueError("canonical_new missing required column 'inchi_key'")

    # Normalize merge key deterministically
    canonical_new = canonical_new.copy()
    canonical_new["inchi_key"] = canonical_new["inchi_key"].astype(str).str.strip()
    canonical_new = canonical_new[canonical_new["inchi_key"].notna() & (canonical_new["inchi_key"] != "")]
    canonical_new = _blank_to_nan(canonical_new)

    db_path = Path(canonical_db_path)

    if db_path.exists():
        canonical_old = pd.read_excel(db_path, engine="openpyxl")
        if "inchi_key" not in canonical_old.columns:
            raise ValueError(f"Existing canonical DB missing 'inchi_key': {canonical_db_path}")

        canonical_old = canonical_old.copy()
        canonical_old["inchi_key"] = canonical_old["inchi_key"].astype(str).str.strip()
        canonical_old = canonical_old[canonical_old["inchi_key"].notna() & (canonical_old["inchi_key"] != "")]
        canonical_old = _blank_to_nan(canonical_old)

        old_idx = canonical_old.set_index("inchi_key", drop=False)
        new_idx = canonical_new.set_index("inchi_key", drop=False)

        # Deterministic columns: canonical order + extras sorted
        all_cols = [c for c in CANONICAL_ORDER if (c in old_idx.columns) or (c in new_idx.columns)]
        extras = sorted([c for c in set(old_idx.columns).union(set(new_idx.columns)) if c not in all_cols])
        all_cols = all_cols + extras

        for c in all_cols:
            if c not in old_idx.columns:
                old_idx[c] = np.nan
            if c not in new_idx.columns:
                new_idx[c] = np.nan

        old_idx = old_idx[all_cols]
        new_idx = new_idx[all_cols]

        # Merge rule: prefer new values, but fill missing from old
        merged_idx = new_idx.combine_first(old_idx)
        canonical_merged = merged_idx.reset_index(drop=True)

    else:
        # No existing DB: new becomes DB (deterministic column order)
        present = set(canonical_new.columns)
        all_cols = [c for c in CANONICAL_ORDER if c in present] + sorted([c for c in present if c not in CANONICAL_ORDER])
        canonical_merged = canonical_new[all_cols].copy()

    # Deterministic row order
    canonical_merged = canonical_merged.sort_values("inchi_key").reset_index(drop=True)

    # Deterministic final column order (again)
    present = set(canonical_merged.columns)
    ordered_cols = [c for c in CANONICAL_ORDER if c in present] + sorted([c for c in present if c not in CANONICAL_ORDER])
    canonical_merged = canonical_merged[ordered_cols]

    # Write updated DB atomically
    _atomic_write_xlsx(canonical_merged, db_path)

    # Overwrite audit workbook if requested
    if audit_excel_path and audit_df is not None:
        _atomic_write_xlsx(audit_df, Path(audit_excel_path))

    return canonical_merged

def export_physprops_wide(
    input_excel_path: str,
    output_excel_path: str,
    sheet_name: str = None,
):
    """
    Export a wide, governed physprops table with a FIXED, frozen schema.

    Governance rules:
    - Always output the exact same column set (order is stable).
    - Do NOT drop columns if they are empty.
    - If an expected column is missing from the input, create it as all-blank.

    Notes:
    - This module remains I/O-only (no chemical logic, no unit conversions).
    """

    EXPORT_COLUMNS = [
        # --- Identity (ALWAYS PRESENT; makes export joinable) ---
        "CAS_ID",
        "inchi_key",        # canonical join key (new)
        "final_inchikey",   # legacy alias (optional to keep)
        "final_inchi",
        "final_smiles",
        "normalized_input",
        "computed_mw",
        "computed_exact_mass",
        "computed_clogp",
        "computed_tpsa",
        "computed_hbd",
        "computed_hba",
        "computed_rot_bonds",
        "computed_ring_count",
        "computed_fraction_csp3",
        "computed_molar_refractivity",
        "experimental_logp",
        "source_logp",
        "computed_boiling_point_c",
        "computed_vapor_pressure_pa",
        "computed_density_g_ml",
        "computed_water_solubility_mg_l",
        "final_boiling_point_c",
        "final_vapor_pressure_pa",
        "final_water_solubility_mg_l",
        "final_density_g_ml",
        "final_mw",
        "final_exact_mass",
        "final_clogp",
        "final_tpsa",
        "final_hbd",
        "final_hba",
        "final_rot_bonds",
        "final_ring_count",
        "final_fraction_csp3",
        "final_molar_refractivity",
        "experimental_henry_constant_mol_m3_pa",
        "source_henry_constant",
        "henry_constant_mol_m3_Pa_25C",
        "log_henry_constant_mol_m3_Pa_25C",
        "experimental_hsp_delta_d_mpa05",
        "experimental_hsp_delta_p_mpa05",
        "experimental_hsp_delta_h_mpa05",
        "source_hsp",
        "computed_hsp_delta_d_mpa05",
        "computed_hsp_delta_p_mpa05",
        "computed_hsp_delta_h_mpa05",
        "source_hsp_computed",
        "timestamp",
    ]

    df = pd.read_excel(input_excel_path, sheet_name=sheet_name, engine="openpyxl")
    if isinstance(df, dict):
        first = next(iter(df.keys()))
        df = df[first]


    # Accept common InChIKey header variants from inputs
    if "inchi_key" not in df.columns:
        for alt in ("InChIKey", "inchikey", "INCHIKEY", "inchiKey"):
            if alt in df.columns:
                df["inchi_key"] = df[alt]
                break

    # Keep legacy alias too (optional but helpful)
    if "final_inchikey" not in df.columns and "inchi_key" in df.columns:
        df["final_inchikey"] = df["inchi_key"]


    # Ensure canonical key exists for governed export
    if "inchi_key" not in df.columns and "final_inchikey" in df.columns:
        df["inchi_key"] = df["final_inchikey"]

    if "inchi_key" in df.columns:
        df["inchi_key"] = df["inchi_key"].astype(str).str.strip().str.upper()
        df.loc[df["inchi_key"].isin(["", "NAN", "NONE"]), "inchi_key"] = pd.NA


    for c in EXPORT_COLUMNS:
        if c not in df.columns:
            df[c] = pd.NA

    export_df = df[EXPORT_COLUMNS].copy()
    write_xlsx_atomic(export_df, output_excel_path, sheet_name="Sheet1")
    logger.info("Exported governed wide physprops table to %s", output_excel_path)

def _harmonize_identifiers(df: pd.DataFrame) -> pd.DataFrame:
 
    """
    Harmonize CAS/SMILES columns into canonical names and drop legacy duplicates.

    Canonical columns:
      - cas_number
      - smiles

    Legacy synonyms (accepted as inputs but removed from canonical):
      - CAS_ID, cas  -> cas_number
      - SMILES       -> smiles
    """
    df = df.copy()

    # Normalize column names deterministically (strip only; keep original case except known ones)
    cols = {c: str(c).strip() for c in df.columns}
    if any(cols[c] != c for c in df.columns):
        df = df.rename(columns=cols)

    # Helper: treat empty/whitespace strings as missing
    def _empty_to_nan(s: pd.Series) -> pd.Series:
        return s.apply(lambda x: np.nan if isinstance(x, str) and x.strip() == "" else x)

    # If canonical key missing but legacy present, fill it deterministically
    if "inchi_key" in df.columns and df["inchi_key"].isna().all() and "final_inchikey" in df.columns:
        df["inchi_key"] = df["final_inchikey"]

    # Ensure canonical columns exist (as Series) for combine_first chains
    if "cas_number" not in df.columns:
        df["cas_number"] = np.nan
    if "smiles" not in df.columns:
        df["smiles"] = np.nan

    # Normalize candidate synonym columns
    for c in ["cas_number", "CAS_ID", "cas", "smiles", "SMILES"]:
        if c in df.columns:
            df[c] = _empty_to_nan(df[c])

    # CAS: fill cas_number only where missing, from cas then CAS_ID (deterministic precedence)
    if "cas" in df.columns:
        df["cas_number"] = df["cas_number"].combine_first(df["cas"])
    if "CAS_ID" in df.columns:
        df["cas_number"] = df["cas_number"].combine_first(df["CAS_ID"])

    # SMILES: fill smiles only where missing, from SMILES
    if "SMILES" in df.columns:
        df["smiles"] = df["smiles"].combine_first(df["SMILES"])

    # Normalize final canonical text
    df["cas_number"] = df["cas_number"].astype("string").str.strip()
    df["smiles"] = df["smiles"].astype("string").str.strip()

    # Drop legacy synonym columns to prevent duplication in the canonical DB
    drop_cols = [c for c in ["CAS_ID", "cas", "SMILES"] if c in df.columns]
    if drop_cols:
        df = df.drop(columns=drop_cols)

    return df

