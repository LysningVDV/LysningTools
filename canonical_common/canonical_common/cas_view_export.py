# canonical_common/cas_view_export.py
from __future__ import annotations

from pathlib import Path
import pandas as pd
from canonical_common.cas_registry import (
    get_local_db_root,
    read_registry_excel,
    load_or_init_allowlist,
    REGISTRY_SHEET,
)

DB1_SHEET = "canonical"

def find_tools_root(start: Path) -> Path:
    p = start.resolve()
    for parent in [p, *p.parents]:
        if (parent / "Canonical_DB").exists():
            return parent
    return p

def read_db1_canonical(db1_xlsx: Path) -> pd.DataFrame:
    return pd.read_excel(db1_xlsx, sheet_name=DB1_SHEET, engine="openpyxl")


def export_cas_view(
    db1_xlsx: Path,
    db2_xlsx: Path,
    db2_schema_json: Path,
    out_dir: Path,
    view_name_prefix: str = "cas_view",
    customer_id: str | None = None,   # <-- ADD THIS
) -> dict:

    if out_dir is None:
        tools_root = find_tools_root(Path(__file__).resolve())
        out_dir = tools_root / "output" / "Canonical_DB" / "exports_cas_view"

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    allowlist = load_or_init_allowlist(db2_schema_json)
    reg = read_registry_excel(db2_xlsx, allowlist, sheet_name=REGISTRY_SHEET)

    db1 = read_db1_canonical(db1_xlsx)
    if "inchi_key" in db1.columns:
        db1["inchi_key"] = db1["inchi_key"].astype(str).str.upper().str.strip()

    reg["inchi_key"] = reg["inchi_key"].astype(str).str.upper().str.strip()

    # Only joinable rows will match; mixtures/UVCB stay but won't join
    joined = reg.merge(db1, on="inchi_key", how="left", suffixes=("_registry", ""))

    # Joinable-only view: valid + has InChIKey
    status_col = "cas_status"
    joinable_mask = (
        joined["inchi_key"].astype(str).str.strip().ne("")
        & joined[status_col].astype(str).str.lower().eq("valid")
        if status_col in joined.columns else
        joined["inchi_key"].astype(str).str.strip().ne("")
    )
    joined_joinable = joined.loc[joinable_mask].copy()
    # --- Optional customer overlay (DB2 customer_map) ---
    if customer_id:
        cmap = pd.read_excel(
            db2_xlsx,
            sheet_name="customer_map",
            engine="openpyxl",
            dtype=str,
        ).fillna("")

        cmap["customer_id"] = cmap["customer_id"].astype(str).str.strip()
        cmap["cas_number_normalized"] = cmap["cas_number_normalized"].astype(str).str.strip()

        cmap = cmap[cmap["customer_id"] == customer_id].copy()

        # Keep only needed customer overlay columns
        cmap = cmap[["cas_number_normalized", "Customer Code / Code Unique", "Name"]].copy()

        # Ensure join key exists and is normalized in outputs
        if "cas_number_normalized" in joined.columns:
            joined["cas_number_normalized"] = joined["cas_number_normalized"].astype(str).str.strip()
            joined = joined.merge(cmap, on="cas_number_normalized", how="left")
        else:
            raise KeyError("Expected 'cas_number_normalized' column missing from CAS view dataframe (joined).")

        if "cas_number_normalized" in joined_joinable.columns:
            joined_joinable["cas_number_normalized"] = joined_joinable["cas_number_normalized"].astype(str).str.strip()
            joined_joinable = joined_joinable.merge(cmap, on="cas_number_normalized", how="left")
        else:
            raise KeyError("Expected 'cas_number_normalized' column missing from joinable CAS view dataframe (joined_joinable).")

    suffix = f"__{customer_id}" if customer_id else ""
    ts = pd.Timestamp.now("UTC").strftime("%Y%m%dT%H%M%S%fZ")
    xlsx_path = out_dir / f"{view_name_prefix}{suffix}__{ts}.xlsx"
    csv_path = out_dir / f"{view_name_prefix}{suffix}__{ts}.csv"

    # Additional joinable-only outputs
    xlsx_joinable_path = out_dir / f"{view_name_prefix}_joinable{suffix}__{ts}.xlsx"
    csv_joinable_path = out_dir / f"{view_name_prefix}_joinable{suffix}__{ts}.csv"

 
    # Full export
    joined.to_csv(csv_path, index=False, encoding="utf-8")
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as xlw:
        joined.to_excel(xlw, sheet_name="cas_view", index=False)

    # Joinable-only export
    joined_joinable.to_csv(csv_joinable_path, index=False, encoding="utf-8")
    with pd.ExcelWriter(xlsx_joinable_path, engine="openpyxl") as xlw:
        joined_joinable.to_excel(xlw, sheet_name="cas_view_joinable", index=False)

    return {
        "xlsx": xlsx_path,
        "csv": csv_path,
        "rows": len(joined),
        "xlsx_joinable": xlsx_joinable_path,
        "csv_joinable": csv_joinable_path,
        "rows_joinable": len(joined_joinable),
    }