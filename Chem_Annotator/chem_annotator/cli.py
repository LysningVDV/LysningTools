# chem_annotator/cli.py
import argparse
import os
import shutil
from pathlib import Path
from typing import Union
from datetime import datetime
import numpy as np
import pandas as pd

from .io_utils import read_smiles_excel, process_dataframe, write_outputs
from canonical_common.canonical_db import (
    load_or_init_allowlist,
    read_xlsx,
    write_xlsx_atomic,
    sanitize_outgoing,
    upsert_canonical,
)

PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_INFILE = str(PACKAGE_DIR / "SMILES.xlsx")   # lives inside chem_annotator
DEFAULT_SHEET: Union[int, str] = 0
DEFAULT_OUTFILE = "smiles_counts.xlsx"

# Preferred shared canonical folder (same policy as PhysProps)
ONEDRIVE_CANONICAL_ROOT = Path(r"C:\Users\vdevi\OneDrive - Lysning Innovation Consultants B.V\Lysning\Tools\Canonical_DB")
PREFERRED_CANONICAL_DIR = ONEDRIVE_CANONICAL_ROOT  # backward-compat alias

def _choose_canonical_root(preferred: Path, fallback: Path) -> Path:
    """
    Prefer `preferred` if creatable+writable; otherwise fallback.
    Uses a tiny probe file to detect OneDrive/ACL non-writable cases deterministically.
    """
    try:
        preferred.mkdir(parents=True, exist_ok=True)
        probe = preferred / ".chem_annotator_write_probe.tmp"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return preferred
    except Exception:
        return fallback


def main():
    parser = argparse.ArgumentParser(
        description="Annotate SMILES with functional group counts and descriptors."
    )
    parser.add_argument(
        "-i", "--input",
        default=DEFAULT_INFILE,
        help="Input Excel file (default: chem_annotator/SMILES.xlsx)."
    )
    parser.add_argument(
        "-s", "--sheet",
        default=str(DEFAULT_SHEET),
        help="Sheet index or name (default: 0)"
    )
    parser.add_argument(
        "-o", "--output",
        default=DEFAULT_OUTFILE,
        help="Output Excel file name (default: smiles_counts.xlsx)"
    )
    parser.add_argument(
        "--no-canonical",
        action="store_true",
        help="Disable updating the shared canonical database."
    )

    args = parser.parse_args()
    sheet: Union[int, str] = int(args.sheet) if str(args.sheet).isdigit() else args.sheet

    # Require inchi_key unless canonical update is disabled
    df = read_smiles_excel(args.input, sheet, require_inchi_key=not args.no_canonical)

    out_df, invalid, df_empty = process_dataframe(df)

    # Write next to the *input* file (i.e., inside chem_annotator by default)
    write_outputs(out_df, invalid, df_empty, infile=args.input, outfile=args.output)

# ----------------------------------------------------
    # Canonical update (shared deterministic writer)
    # ----------------------------------------------------
    if not args.no_canonical:
        if "inchi_key" not in out_df.columns:
            raise ValueError(
                "Missing required column 'inchi_key' in output. Ensure it is present in input "
                "(or disable canonical update with --no-canonical)."
            )

        # Fallback root = folder containing input
        fallback_root = Path(os.path.dirname(os.path.abspath(args.input)))
        canonical_root = _choose_canonical_root(PREFERRED_CANONICAL_DIR, fallback_root)        
        local_root = os.getenv("CANONICAL_DB_LOCAL_ROOT")
        if local_root:
            canonical_db_path = Path(local_root) / "canonical_physchemprops.xlsx"
        else:
            canonical_db_path = canonical_root / "canonical_physchemprops.xlsx"
        
        print(f"[CONFIG] Canonical schema/audit root (OneDrive): {canonical_root}")
        print(f"[CONFIG] Canonical DB path (local if env set): {canonical_db_path}")


        # Keep audit files (separate per tool, overwrite each run)
        canonical_audit_path = canonical_root / "canonical_audit_chem_annotator.xlsx"

        # New: schema + rejects live next to canonical DB
        schema_json_path = canonical_root / "canonical_schema.json"
        rejected_path = canonical_root / "canonical_physchemprops.rejected_chem_annotator.xlsx"

        # Always report chosen target paths (audit-friendly)
        print(f"[INFO] Canonical root chosen: {canonical_root}")
        print(f"[INFO] Canonical DB path: {canonical_db_path}")
        print(f"[INFO] Canonical audit path: {canonical_audit_path}")
        print(f"[INFO] Canonical schema path: {schema_json_path}")
        print(f"[INFO] Canonical rejected path: {rejected_path}")

        # --- 1) Load/freeze schema allowlist (stops column growth) ---        

        allowlist = load_or_init_allowlist(schema_json_path)
        print(f"[DEBUG] allowlist_len={len(allowlist)} has_exp_henry={'experimental_henry_constant_mol_m3_pa' in allowlist} has_base_henry={'henry_constant_mol_m3_Pa_25C' in allowlist}")
        # --- 2) Sanitize outgoing batch (promote ids, allowlist, dedupe in-batch) ---
        incoming, rejected = sanitize_outgoing(
            out_df,
            tool_name="chem_annotator",
            allowlist=allowlist
        )

        print("incoming shape:", incoming.shape, "rejected shape:", rejected.shape)
        print("incoming all-zero cols:", int((incoming.drop(columns=['inchi_key'], errors='ignore').fillna(0)==0).all(axis=0).sum()))

        # --- 3) Upsert into existing canonical (one row per inchi_key, deterministic) ---
        if incoming is None or incoming.empty:
            print("[WARNING] Canonical update skipped: no valid rows after sanitization.")
            merged_rows = 0
        else:
            if canonical_db_path.exists() and canonical_db_path.stat().st_size >= 50_000:
                try:
                    existing = read_xlsx(canonical_db_path, sheet_name="canonical")
                except ValueError:
                    existing = read_xlsx(canonical_db_path, sheet_name=0)
            else:
                existing = pd.DataFrame(columns=allowlist)
            merged = upsert_canonical(
                existing=existing,
                incoming=incoming,
                tool_name="chem_annotator",
                allowlist=allowlist
            )

            merged.columns = [str(c).strip() for c in merged.columns]
            merged = merged.reindex(columns=allowlist)

            write_xlsx_atomic(merged, str(canonical_db_path), sheet_name="canonical",min_size_bytes=50_000)  # Avoid Excel truncation of very small files
            merged_rows = len(merged)
            print(f"[OK] Canonical DB updated: {canonical_db_path} (rows={merged_rows})")            
            backup_dir = canonical_root / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = backup_dir / f"canonical_physchemprops__{stamp}.xlsx"
            shutil.copy2(str(canonical_db_path), str(backup_path))
            print(f"[OK] Canonical DB backup written: {backup_path}")

        # --- 4) Write rejected rows (missing/invalid inchi_key), if any ---
        if rejected is not None and not rejected.empty:
            write_xlsx_atomic(rejected, str(rejected_path), sheet_name="rejected")
            print(f"[WARNING] Rejected rows written: {rejected_path} (rows={len(rejected)})")
            rejected_rows = int(len(rejected))
        else:
            rejected_rows = 0
            print("[INFO] No rejected rows produced in this run.")

        # --- 5) Tool-specific canonical audit (overwrite each run) ---
        output_file_path = (fallback_root / args.output).resolve()

        audit_df = pd.DataFrame([{
            "tool": "CHEM_Annotator",
            "timestamp_utc": pd.Timestamp.utcnow().isoformat(),
            "input_file": str(Path(args.input).resolve()),
            "output_file": str(output_file_path),
            "rows_out": int(len(out_df)),
            "rows_invalid": int(len(invalid)) + int(len(df_empty)),
            "rows_incoming_valid": int(len(incoming)) if incoming is not None else 0,
            "rows_rejected": int(rejected_rows),
            "rows_canonical_after": int(merged_rows),
            "canonical_db_path": str(canonical_db_path.resolve()),
            "schema_json_path": str(schema_json_path.resolve()),
            "rejected_path": str(rejected_path.resolve()),
        }])

        write_xlsx_atomic(audit_df, str(canonical_audit_path), sheet_name="audit")  
        print(f"[OK] Canonical DB updated: {canonical_db_path}")
        print(f"[OK] Canonical audit written: {canonical_audit_path}")


if __name__ == "__main__":
    main()

