from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path
from typing import Optional

import pandas as pd


# -------------------------
# Helpers
# -------------------------

def utc_stamp() -> str:
    # collision-proof
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def find_tools_root(start: Path) -> Path:
    p = start.resolve()
    for parent in [p, *p.parents]:
        if (parent / "Canonical_DB").exists():
            return parent
    return p


def run(cmd: list[str], cwd: Optional[Path] = None) -> None:
    print("\nRUN:", " ".join(cmd))
    subprocess.check_call(cmd, cwd=str(cwd) if cwd else None)


def latest_file(glob_pattern: str, base: Path) -> Path:
    files = sorted(base.glob(glob_pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError(f"No files match pattern: {base / glob_pattern}")
    return files[0]


def read_joinable_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def pick_col(df: pd.DataFrame, candidates: list[str]) -> str:
    cols = {c.lower(): c for c in df.columns}
    for c in candidates:
        if c.lower() in cols:
            return cols[c.lower()]
    raise KeyError(f"None of these columns found: {candidates}. Available: {list(df.columns)}")


# -------------------------
# Customer map feed builder
# -------------------------

def build_customer_map_feed(exploded_xlsx: Path, out_csv: Path) -> int:
    df = pd.read_excel(exploded_xlsx, engine="openpyxl", dtype=str).fillna("")

    # Your Structurer exploded output should contain these:
    required = ["customer_id", "timestamp_seen_utc", "Customer Code / Code Unique", "Name", "CAS", "CAS_valid"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Exploded file missing columns {missing}. Found: {list(df.columns)}")

    out = df[required].copy()
    out["CAS"] = out["CAS"].astype(str).str.strip()
    out = out[out["CAS"].ne("")]

    out["CAS_valid"] = out["CAS_valid"].astype(str)
    out = out[~out["CAS_valid"].str.lower().str.contains("invalid")]

    out = out.sort_values("timestamp_seen_utc")
    out = out.drop_duplicates(subset=["customer_id", "CAS"], keep="last")

    out = out.rename(columns={"CAS": "cas_number_normalized", "CAS_valid": "cas_validity"})

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_csv, index=False, encoding="utf-8")
    return len(out)


# -------------------------
# Input builders for tools
# -------------------------

def write_chem_annotator_input_from_joinable(joinable_csv: Path, out_xlsx: Path) -> int:
    df = read_joinable_csv(joinable_csv)

    col_ik = pick_col(df, ["inchi_key", "InChIKey", "inchikey"])
    col_smiles = pick_col(df, ["smiles", "SMILES"])
    col_cas = pick_col(df, ["cas_number_normalized", "CAS", "cas", "CAS_ID"])

    d = df[[col_cas, col_ik, col_smiles]].copy()

    d[col_ik] = d[col_ik].astype(str).str.strip().str.upper()
    d[col_smiles] = d[col_smiles].astype(str).str.strip()
    d[col_cas] = d[col_cas].astype(str).str.strip()

    d = d[d[col_ik].ne("") & d[col_smiles].ne("") & d[col_cas].ne("")] \
        .drop_duplicates(subset=[col_ik]).reset_index(drop=True)

    # IMPORTANT: write only CAS_ID (NOT both cas and CAS_ID)
    d = d.rename(columns={col_cas: "CAS_ID", col_ik: "inchi_key", col_smiles: "smiles"})

    out_xlsx.parent.mkdir(parents=True, exist_ok=True)
    d[["CAS_ID", "inchi_key", "smiles"]].to_excel(out_xlsx, index=False, engine="openpyxl")
    return len(d)


def write_physprops_input_from_joinable(joinable_csv: Path, out_xlsx: Path) -> int:
    df = read_joinable_csv(joinable_csv)
    col_ik = pick_col(df, ["inchi_key", "InChIKey", "inchikey"])

    d = pd.DataFrame({"InChIKey": df[col_ik].astype(str).str.strip().str.upper()})
    d = d[d["InChIKey"].ne("")].drop_duplicates().reset_index(drop=True)

    out_xlsx.parent.mkdir(parents=True, exist_ok=True)
    d.to_excel(out_xlsx, index=False, engine="openpyxl")
    return len(d)


# -------------------------
# Main runner
# -------------------------

def main() -> int:
    tools_root = find_tools_root(Path(__file__).resolve())
    stamp = utc_stamp()

    ap = argparse.ArgumentParser(description="Single-customer pipeline runner (Structurer -> Resolver -> DB2 customer_map -> CAS view -> Chem_Annotator -> PhysProps -> CAS view).")
    ap.add_argument("input_xlsx", type=Path, help="Customer input Excel file")
    ap.add_argument("--customer-id", required=True, help="Customer short code (e.g., MANE)")

    ap.add_argument("--sheet", default=None, help="Sheet name (optional)")
    ap.add_argument("--cas-col", default="CAS", help="CAS column header (default: CAS)")
    ap.add_argument("--code-col", default="Code Unique", help="Customer code column header (default: Code Unique)")
    ap.add_argument("--name-col", default="Designation", help="Name column header (default: Designation)")

    ap.add_argument("--skip-chem", action="store_true", help="Skip Chem_Annotator step")
    ap.add_argument("--skip-physprops", action="store_true", help="Skip PhysProps step")

    args = ap.parse_args()

    # Where we’ll log runner artifacts (optional but handy)
    runner_out = tools_root / "output" / "PipelineRunner"
    runner_out.mkdir(parents=True, exist_ok=True)
    runner_manifest_path = runner_out / f"pipeline_manifest__{args.customer_id}__{stamp}.json"

    # 1) CAS_Structurer
    # Note: uses strict columns via your Structurer logic.
    # 1) CAS_Structurer must be run with cwd pointing at Tools/CAS_Structurer
    cas_structurer_cwd = tools_root / "CAS_Structurer"

    cmd_struct = [
        sys.executable, "-m", "cas_structurer",
        str(args.input_xlsx.resolve()),
        "--customer-id", args.customer_id,
        "--cas-col", args.cas_col,
        "--code-col", args.code_col,
        "--name-col", args.name_col,
    ]
    if args.sheet:
        cmd_struct += ["--sheet", str(args.sheet)]
    cmd_struct += ["--outdir", str((tools_root / "output" / "CAS_Structurer").resolve())]
    if not cas_structurer_cwd.exists():
      raise FileNotFoundError(f"CAS_Structurer folder not found: {cas_structurer_cwd}")

    run(cmd_struct, cwd=cas_structurer_cwd)

    # Locate latest Structurer manifest, then exploded path
    # Structurer outputs may be in standardized Tools/output/CAS_Structurer OR local Tools/CAS_Structurer/output
    struct_dir_std = tools_root / "output" / "CAS_Structurer"
    struct_dir_local = tools_root / "CAS_Structurer" / "output"

    if struct_dir_std.exists():
        struct_dir = struct_dir_std
    elif struct_dir_local.exists():
        struct_dir = struct_dir_local
    else:
        raise FileNotFoundError(
            f"Neither structurer output dir exists:\n"
            f"  - {struct_dir_std}\n"
            f"  - {struct_dir_local}\n"
            f"Run CAS_Structurer once (or pass --outdir) to generate outputs."
        )
    struct_manifest = latest_file(f"{args.input_xlsx.stem}_manifest_*.json", struct_dir)
    struct_info = json.loads(struct_manifest.read_text(encoding="utf-8"))
    exploded_xlsx = Path(struct_info["outputs"]["exploded_xlsx"]) if "outputs" in struct_info else None
    if exploded_xlsx is None or not exploded_xlsx.exists():
        # fallback: pick latest exploded
        exploded_xlsx = latest_file(f"{args.input_xlsx.stem}_exploded_*.xlsx", struct_dir)

    # 2) CASResolver (DB2 registry update is inside resolver)
    cmd_res = [
        sys.executable, "-m", "lysning_casresolver.main",
        str(exploded_xlsx),
    ]
    run(cmd_res, cwd=tools_root)

    # 3) Build customer_map_feed.csv (canonical location used by upsert script)
    feed_csv = tools_root / "Canonical_DB" / "exports_pipeline" / "customer_map_feed.csv"
    feed_rows = build_customer_map_feed(exploded_xlsx, feed_csv)
    print(f"[OK] customer_map_feed.csv rows: {feed_rows}")

    # 4) Upsert DB2 customer_map
    run([sys.executable, str(tools_root / "Canonical_DB" / "scripts" / "upsert_customer_map.py")], cwd=tools_root)

    # 5) Export per-customer CAS views
    run([sys.executable, str(tools_root / "Canonical_DB" / "scripts" / "smoke_db2_view_export.py"),
         "--customer-id", args.customer_id], cwd=tools_root)

    # Latest joinable per-customer view CSV will be input to Chem_Annotator & PhysProps
    cas_view_dir = tools_root / "output" / "Canonical_DB" / "exports_cas_view"
    joinable_csv = latest_file(f"cas_view_joinable__{args.customer_id}__*.csv", cas_view_dir)

    # 6) Chem_Annotator
    chem_input = tools_root / "Chem_Annotator" / "smiles.xlsx"
    chem_rows = write_chem_annotator_input_from_joinable(joinable_csv, chem_input)
    print(f"[OK] Chem_Annotator input rows: {chem_rows}")

    if not args.skip_chem:
        run([sys.executable, "-m", "chem_annotator.cli", "-i", str(chem_input)], cwd=tools_root)

        # Re-export CAS views after Chem_Annotator updates DB1
        run([sys.executable, str(tools_root / "Canonical_DB" / "scripts" / "smoke_db2_view_export.py"),
             "--customer-id", args.customer_id], cwd=tools_root)

        # Refresh joinable CSV path after re-export
        joinable_csv = latest_file(f"cas_view_joinable__{args.customer_id}__*.csv", cas_view_dir)

    # 7) PhysProps
    phys_input = tools_root / "PhysProps" / "input_inchikey.xlsx"
    phys_rows = write_physprops_input_from_joinable(joinable_csv, phys_input)
    print(f"[OK] PhysProps input rows: {phys_rows}")

    if not args.skip_physprops:
        run([sys.executable, "-m", "physprops.main", str(phys_input), "--log", "INFO"], cwd=tools_root)

        # Final re-export CAS views after PhysProps
        run([sys.executable, str(tools_root / "Canonical_DB" / "scripts" / "smoke_db2_view_export.py"),
             "--customer-id", args.customer_id], cwd=tools_root)

    # Runner manifest
    manifest = {
        "tool": "pipeline_runner",
        "run_stamp_utc": stamp,
        "customer_id": args.customer_id,
        "input_xlsx": str(args.input_xlsx.resolve()),
        "structurer_manifest": str(struct_manifest.resolve()),
        "exploded_xlsx": str(exploded_xlsx.resolve()),
        "customer_map_feed_csv": str(feed_csv.resolve()),
        "latest_joinable_csv": str(joinable_csv.resolve()),
        "chem_input": str(chem_input.resolve()),
        "phys_input": str(phys_input.resolve()),
        "outputs_root": str((tools_root / "output").resolve()),
    }
    runner_manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("[OK] Runner manifest:", runner_manifest_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())