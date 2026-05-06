
import os
import glob
from datetime import datetime
from typing import List, Dict, Union, Tuple
import pandas as pd
from rdkit import RDLogger
from .utils import clean_smiles
from .aggregator import features_for_smiles
from .schema import make_empty_features
from canonical_common.canonical_db import (
    write_xlsx_atomic,
)

RDLogger.DisableLog("rdApp.error")  # Silence RDKit parse messages


def read_smiles_excel(
    path: str,
    sheet: Union[int, str] = 0,
    require_inchi_key: bool = True,
) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=sheet, engine="openpyxl")

    # -----------------------------------------------------
    # Normalize column names deterministically (case/spacing)
    # -----------------------------------------------------
    rename = {}
    for c in df.columns:
        key = str(c).strip().lower()
        if key == "smiles":
            rename[c] = "SMILES"
        elif key in ("inchi_key", "inchi key", "inchikey", "inchi-key"):
            rename[c] = "inchi_key"
        elif key in ("cas", "cas_id", "casid"):
            rename[c] = "cas"

    if rename:
        df = df.rename(columns=rename)

    # -----------------------------------------------------
    # Validate required columns (after normalization!)
    # -----------------------------------------------------
    missing = []

    if "SMILES" not in df.columns:
        missing.append("SMILES")

    # At least one CAS column must exist
    has_cas = ("cas" in df.columns) or ("CAS_ID" in df.columns)
    if not has_cas:
        missing.append("cas (or CAS_ID)")

    # Require inchi_key only if canonical update is enabled
    if require_inchi_key and "inchi_key" not in df.columns:
        missing.append("inchi_key")

    if missing:
        raise ValueError(f"Missing required column(s): {missing}")

    # -----------------------------------------------------
    # Normalize CAS columns for downstream compatibility
    # -----------------------------------------------------
    if "CAS_ID" not in df.columns and "cas" in df.columns:
        df["CAS_ID"] = df["cas"]
    elif "cas" not in df.columns and "CAS_ID" in df.columns:
        df["cas"] = df["CAS_ID"]

    # -----------------------------------------------------
    # Normalize InChIKey deterministically
    # -----------------------------------------------------
    if "inchi_key" in df.columns:
        df["inchi_key"] = df["inchi_key"].astype(str).str.strip()

    return df

def process_dataframe(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[Dict], pd.DataFrame]:
    # Clean SMILES, keep a copy of originals
    df["SMILES_CLEAN"] = df["SMILES"].apply(clean_smiles)

    # Separate empties after cleaning
    empty_mask = df["SMILES_CLEAN"].eq("")

    # Keep useful identifiers for audit/canonical use (if present)
    empty_cols = [c for c in ["CAS_ID", "cas", "inchi_key", "SMILES"] if c in df.columns]
    df_empty = df.loc[empty_mask, empty_cols].copy()
    df_empty["Reason"] = "Empty after cleaning"
    df_work = df.loc[~empty_mask].copy()

    # Process rows and collect invalids (with reasons)
    results: List[Dict] = []
    invalid: List[Dict] = []

    # Include inchi_key (if present) in iteration so invalid records can carry it
    work_cols = [c for c in ["CAS_ID", "cas", "inchi_key", "SMILES", "SMILES_CLEAN"] if c in df_work.columns]

    # Avoid double parsing: features_for_smiles() already parses and returns Valid=0 on failure
    for _, row in df_work[work_cols].iterrows():
        smi = row["SMILES_CLEAN"]
        feats = features_for_smiles(smi)

        if feats.get("Valid") == 0:
            inv = {"SMILES": row["SMILES"], "Reason": "Failed to parse"}
            if "CAS_ID" in df_work.columns:
                inv["CAS_ID"] = row["CAS_ID"]
            if "cas" in df_work.columns:
                inv["cas"] = row["cas"]
            if "inchi_key" in df_work.columns:
                inv["inchi_key"] = row["inchi_key"]
            invalid.append(inv)

        results.append(feats)

    res_df = pd.DataFrame(results).reset_index(drop=True)
    out_df = pd.concat(
        [df_work.reset_index(drop=True).drop(columns=["SMILES_CLEAN"]), res_df],
        axis=1,
    )

    # Append the rows that were empty after cleaning (schema-complete, mark invalid)
    if not df_empty.empty:
        defaults = make_empty_features()
        df_empty_out = df_empty.copy().drop(columns=["Reason"])

        # Add defaults in one join to avoid pandas fragmentation warnings
        defaults_df = pd.DataFrame([defaults] * len(df_empty_out), index=df_empty_out.index)
        df_empty_out = pd.concat([df_empty_out, defaults_df], axis=1)

        out_df = pd.concat([out_df, df_empty_out], axis=0, ignore_index=True)

    return out_df, invalid, df_empty


def write_outputs(
    out_df: pd.DataFrame,
    invalid: List[Dict],
    df_empty: pd.DataFrame,
    infile: str,
    outfile: str = "smiles_counts.xlsx",
):
    outdir = os.path.dirname(os.path.abspath(infile))  # write next to your input
    excel_path = os.path.join(outdir, outfile)
    csv_path = os.path.join(outdir, "smiles_counts.csv")

    print(f"[INFO] Rows processed: {len(out_df)} Columns: {len(out_df.columns)}")
    try:
        write_xlsx_atomic(out_df, str(excel_path), sheet_name="Sheet1", min_size_bytes=0)
        print(f"[OK] Excel written to: {excel_path}")
    except (PermissionError, OSError):
        excel_path = os.path.join(outdir, f"smiles_counts_{datetime.now():%Y%m%d_%H%M%S}.xlsx")
        write_xlsx_atomic(out_df, str(excel_path), sheet_name="Sheet1", min_size_bytes=0)

        print(f"[WARN] '{outfile}' was in use, wrote fallback to: {excel_path}")

    out_df.to_csv(csv_path, index=False)
    print(f"[OK] CSV written to: {csv_path}")

    # Show a quick directory listing for sanity
    pattern = os.path.join(outdir, "smiles_counts*")
    found = [os.path.basename(p) for p in glob.glob(pattern)]
    print("[INFO] Files matching 'smiles_counts*' in output folder:", found)

    # Save invalids report (if any)
    invalid_rows = invalid + df_empty.to_dict(orient="records")
    if invalid_rows:
        invalid_path = os.path.join(outdir, "invalid_smiles.csv")
        pd.DataFrame(invalid_rows).to_csv(invalid_path, index=False)
        print(f"[INFO] Invalid/empty rows listed in: {invalid_path}")

