import datetime as dt
from pathlib import Path

import pandas as pd

from .cas_logic import (
    split_cas_cell,
    is_all_zero_cas_like,
    is_valid_cas,
    build_evidence_indexes,
    normalize_and_repair_token,
    build_fixed_cas_cell,
)


def process_file(input_path: Path, sheet: str | None, outdir: Path) -> tuple[Path, Path]:
    # Default to first sheet when not specified
    sheet_name = sheet if sheet is not None else 0
    df = pd.read_excel(input_path, engine="openpyxl", sheet_name=sheet_name)

    required = ["CAS", "Code Unique", "Designation"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}. Found: {list(df.columns)}")

    by_code, by_desig = build_evidence_indexes(df)
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")

    # Output 1: exploded
    rows = []
    for _, r in df.iterrows():
        code = r.get("Code Unique")
        desig = r.get("Designation")

        for tok in split_cas_cell(r.get("CAS")):
            cas_out, status = normalize_and_repair_token(tok, code, desig, by_code, by_desig)
            if not str(cas_out).strip():
                continue
            if is_all_zero_cas_like(cas_out):
                continue
            rows.append(
                {"CAS": cas_out, "Code Unique": code, "Designation": desig, "CAS_valid": status}
            )

    exploded = pd.DataFrame(rows)
    if not exploded.empty:
        exploded = exploded.drop_duplicates(
            subset=["CAS", "Code Unique", "Designation"], keep="first"
        )

    # Output 2: first-valid focus + FixedCAS string
    first_tokens = []
    first_comments = []
    fixed_cells = []

    for _, r in df.iterrows():
        code = r.get("Code Unique")
        desig = r.get("Designation")

        toks = split_cas_cell(r.get("CAS"))
        first_tok = ""
        for t in toks:
            if str(t).strip():
                first_tok = t
                break

        if not first_tok:
            first_tokens.append("")
            first_comments.append("invalid (original: )")
        else:
            cas_out, status = normalize_and_repair_token(first_tok, code, desig, by_code, by_desig)
            # Preference is automatically for a fixed-first-token if available
            first_tokens.append(cas_out)
            first_comments.append(status)

        fixed_cells.append(build_fixed_cas_cell(r.get("CAS"), code, desig, by_code, by_desig))

    first_valid_df = df[["Code Unique", "Designation", "CAS"]].copy()
    first_valid_df["FirstCAS"] = first_tokens
    first_valid_df["FirstCAS_comment"] = first_comments
    first_valid_df["FixedCAS"] = fixed_cells
    first_valid_df = first_valid_df.drop_duplicates(
        subset=["Code Unique", "Designation", "CAS"], keep="first"
    )

    outdir.mkdir(parents=True, exist_ok=True)
    stem = input_path.stem
    out1 = outdir / f"{stem}_exploded_{ts}.xlsx"
    out2 = outdir / f"{stem}_first_valid_{ts}.xlsx"

    exploded.to_excel(out1, index=False, engine="openpyxl")
    first_valid_df.to_excel(out2, index=False, engine="openpyxl")

    return out1, out2