from __future__ import annotations
import argparse
import os
from pathlib import Path

import pandas as pd

from canonical_common.cas_registry import (
    get_db2_local_paths,
    load_or_init_allowlist,
    read_registry_excel,
    REGISTRY_SHEET,
)
from canonical_common.cas_view_export import export_cas_view


def _repo_root_from_this_file() -> Path:
    # Canonical_DB/scripts/smoke_db2_view_export.py -> repo root is 2 levels up from Canonical_DB
    return Path(__file__).resolve().parents[2]


def main() -> int:
    repo_root = _repo_root_from_this_file()
    ap = argparse.ArgumentParser(description="SMOKE: DB2->DB1 CAS view export")
    ap.add_argument("--customer-id", default=None, help="Customer ID for per-customer CAS view export (e.g., MANE)")
    args = ap.parse_args()

    # --- Paths (governance + local) ---
    schema_json = repo_root / "Canonical_DB" / "cas_registry_schema.json"
    out_dir = repo_root / "output" / "Canonical_DB" / "exports_cas_view"
    out_dir.mkdir(parents=True, exist_ok=True)



    # DB1 local truth store
    local_root = os.environ.get("CANONICAL_DB_LOCAL_ROOT", "").strip()
    if not local_root:
        raise EnvironmentError("CANONICAL_DB_LOCAL_ROOT is not set.")
    db1_xlsx = Path(local_root) / "canonical_physchemprops.xlsx"

    # DB2 local registry
    db2_paths = get_db2_local_paths()
    db2_xlsx = db2_paths["xlsx"]

    print("=== SMOKE: DB2->DB1 CAS VIEW EXPORT ===")
    print(f"Repo root: {repo_root}")
    print(f"DB1 local: {db1_xlsx}")
    print(f"DB2 local: {db2_xlsx}")
    print(f"Schema:   {schema_json}")
    print(f"Out dir:  {out_dir}")
    print()

    # --- Basic existence checks ---
    if not db1_xlsx.exists():
        print(f"ERROR: DB1 not found: {db1_xlsx}")
        return 2
    if not db2_xlsx.exists():
        print(f"ERROR: DB2 not found: {db2_xlsx}")
        return 3

    # --- Load DB2 registry (sanity) ---
    allowlist = load_or_init_allowlist(schema_json)
    reg = read_registry_excel(db2_xlsx, allowlist, sheet_name=REGISTRY_SHEET)

    # Summary stats
    total = len(reg)
    joinable = reg["inchi_key"].astype(str).str.strip().ne("").sum() if "inchi_key" in reg.columns else 0
    ambiguous = (reg.get("cas_status", "").astype(str).str.lower() == "ambiguous").sum() if "cas_status" in reg.columns else 0
    mixtures = reg.get("cas_status", "").astype(str).str.lower().isin(["mixture", "uvcb"]).sum() if "cas_status" in reg.columns else 0

    print(f"DB2 registry rows: {total}")
    print(f"  joinable (has inchi_key): {joinable}")
    print(f"  ambiguous: {ambiguous}")
    print(f"  mixture/uvcb: {mixtures}")
    print()

    if total == 0:
        print("WARNING: DB2 registry is empty. Export will still run but output will have 0 rows.")
    if joinable == 0:
        print("WARNING: No joinable inchi_keys found in DB2. Join will produce mostly empty DB1 columns.")

    # --- Export CAS view ---
    result = export_cas_view(
        db1_xlsx=db1_xlsx,
        db2_xlsx=db2_xlsx,
        db2_schema_json=schema_json,
        out_dir=out_dir,
        view_name_prefix="cas_view",
        customer_id=args.customer_id,
    )

    print("Export complete:")
    print(f"  rows (full): {result.get('rows')}")
    print(f"  xlsx (full): {result.get('xlsx')}")
    print(f"  csv  (full): {result.get('csv')}")
    print()

    # Optional joinable-only outputs (if exporter returns them)
    if "rows_joinable" in result or "xlsx_joinable" in result or "csv_joinable" in result:
        print("Joinable export complete:")
        print(f"  rows (joinable): {result.get('rows_joinable')}")
        print(f"  xlsx (joinable): {result.get('xlsx_joinable')}")
        print(f"  csv  (joinable): {result.get('csv_joinable')}")
        print()

    # --- Minimal validation: output exists and is non-trivial ---
    xlsx_path = Path(result["xlsx"])
    csv_path = Path(result["csv"])

    if not xlsx_path.exists():
        print("ERROR: Expected XLSX output not found.")
        return 10
    if not csv_path.exists():
        print("ERROR: Expected CSV output not found.")
        return 11

    # Optional: check file size sanity (avoid 0-byte or tiny exports)
    if xlsx_path.stat().st_size < 1000:
        print(f"WARNING: XLSX output is suspiciously small: {xlsx_path.stat().st_size} bytes")
    if csv_path.stat().st_size < 10:
        print(f"WARNING: CSV output is suspiciously small: {csv_path.stat().st_size} bytes")

    print("SMOKE OK ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())