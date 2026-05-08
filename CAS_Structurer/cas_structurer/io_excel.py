import datetime as dt
from pathlib import Path
import json
import pandas as pd
from .cas_logic import (
    split_cas_cell,
    is_all_zero_cas_like,
    build_evidence_indexes,
    normalize_and_repair_token,
    build_fixed_cas_cell,
)

def process_file(
    input_path: Path,
    sheet: str | None,
    outdir: Path,
    customer_id: str,
    cas_col: str,
    code_col: str,
    name_col: str,
    strict: bool = True,
) -> tuple[Path, Path, Path]:

    # Default to first sheet when not specified
    sheet_name = sheet if sheet is not None else 0
    df = pd.read_excel(input_path, engine="openpyxl", sheet_name=sheet_name)
    
    missing = [c for c in (cas_col, code_col, name_col) if c not in df.columns]
    if missing and strict:
        raise ValueError(
            "Missing required columns: "
            + ", ".join(missing)
            + f"\nFound columns: {list(df.columns)}"
            + "\nFix: pass correct --cas-col/--code-col/--name-col for this file."
        )

    # Strict column presence check: use selected headers (not hard-coded defaults)
    required = [cas_col, code_col, name_col]
    missing = [c for c in required if c not in df.columns]
    if missing and strict:
        raise ValueError(
            f"Missing required columns: {missing}\n"
            f"Found columns: {list(df.columns)}\n"
            f"Fix: pass correct --cas-col/--code-col/--name-col for this file."
        )

    by_code, by_desig = build_evidence_indexes(df)
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")

    # Build evidence indexes using the selected columns, but mapped onto the expected names
    df_evidence = df.copy()
    df_evidence["CAS"] = df[cas_col]
    df_evidence["Code Unique"] = df[code_col]
    df_evidence["Designation"] = df[name_col]
    by_code, by_desig = build_evidence_indexes(df_evidence)

    # Output 1: exploded
    run_ts_utc = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%S%fZ")  # collision-proof stamp
    timestamp_seen_utc = dt.datetime.now(dt.UTC).isoformat()

    rows = []
    for _, r in df.iterrows():
        code = r.get(code_col)
        name = r.get(name_col)  # store exactly as given; do NOT normalize

        for tok in split_cas_cell(r.get(cas_col)):
            cas_out, status = normalize_and_repair_token(tok, code, name, by_code, by_desig)
            if not str(cas_out).strip():
                continue
            if is_all_zero_cas_like(cas_out):
                continue

            rows.append(
                {
                    # standardized metadata (your governance choices)
                    "customer_id": customer_id,
                    "timestamp_seen_utc": timestamp_seen_utc,
                    "Customer Code / Code Unique": code,
                    "Name": name,

                    # CAS results
                    "CAS": cas_out,
                    "CAS_valid": status,
                }
            )

    exploded = pd.DataFrame(rows)

    if not exploded.empty:
        exploded = exploded.drop_duplicates(
            subset=["customer_id", "CAS", "Customer Code / Code Unique", "Name"],
            keep="first",
        )

    # Output 2: first-valid focus + FixedCAS string
    first_tokens = []
    first_comments = []
    fixed_cells = []

    for _, r in df.iterrows():
        code = r.get(code_col)
        name = r.get(name_col)  # exact as given
        cas_cell = r.get(cas_col)

        toks = split_cas_cell(cas_cell)
        first_tok = ""
        for t in toks:
            if str(t).strip():
                first_tok = t
                break

        if not first_tok:
            first_tokens.append("")
            first_comments.append("invalid (original: )")
        else:
            cas_out, status = normalize_and_repair_token(first_tok, code, name, by_code, by_desig)
            first_tokens.append(cas_out)
            first_comments.append(status)

        fixed_cells.append(build_fixed_cas_cell(cas_cell, code, name, by_code, by_desig))

    # Build the "first valid" dataframe using selected input columns, but standardized output headers
    first_valid_df = df[[code_col, name_col, cas_col]].copy()
    first_valid_df = first_valid_df.rename(
        columns={
            code_col: "Customer Code / Code Unique",
            name_col: "Name",
            cas_col: "CAS",
        }
    )

    # Add the derived columns
    first_valid_df["FirstCAS"] = first_tokens
    first_valid_df["FirstCAS_comment"] = first_comments
    first_valid_df["FixedCAS"] = fixed_cells

    # Add run metadata (same as exploded output)
    first_valid_df["customer_id"] = customer_id
    first_valid_df["timestamp_seen_utc"] = timestamp_seen_utc

    # Dedupe deterministically
    first_valid_df = first_valid_df.drop_duplicates(
        subset=["customer_id", "Customer Code / Code Unique", "Name", "CAS"],
        keep="first"
    )

    # Ensure output folder exists
    outdir.mkdir(parents=True, exist_ok=True)

    stem = input_path.stem

    out1 = outdir / f"{stem}_exploded_{run_ts_utc}.xlsx"
    out2 = outdir / f"{stem}_first_valid_{run_ts_utc}.xlsx"
    manifest_path = outdir / f"{stem}_manifest_{run_ts_utc}.json"

    # Write Excel outputs
    exploded.to_excel(out1, index=False, engine="openpyxl")
    first_valid_df.to_excel(out2, index=False, engine="openpyxl")

    # Build manifest JSON
    manifest = {
        "tool": "cas_structurer",
        "run_stamp_utc": run_ts_utc,
        "timestamp_seen_utc": timestamp_seen_utc,
        "customer_id": customer_id,
        "input_file": str(input_path.resolve()),
        "sheet": sheet,
        "column_mapping": {
            "cas_col": cas_col,
            "code_col": code_col,
            "name_col": name_col,
            "output_customer_code_col": "Customer Code / Code Unique",
            "output_name_col": "Name",
        },
        "outputs": {
            "exploded_xlsx": str(out1.resolve()),
            "first_valid_xlsx": str(out2.resolve()),
        },
        "counts": {
            "rows_input": int(len(df)),
            "rows_exploded": int(len(exploded)),
            "rows_first_valid": int(len(first_valid_df)),
            "unique_cas_exploded": int(exploded["CAS"].nunique()) if not exploded.empty else 0,
        },
    }

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    return out1, out2, manifest_path


