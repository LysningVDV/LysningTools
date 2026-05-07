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


def read_db1_canonical(db1_xlsx: Path) -> pd.DataFrame:
    return pd.read_excel(db1_xlsx, sheet_name=DB1_SHEET, engine="openpyxl")


def export_cas_view(
    db1_xlsx: Path,
    db2_xlsx: Path,
    db2_schema_json: Path,
    out_dir: Path,
    view_name_prefix: str = "cas_view",
) -> dict:
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

    ts = pd.Timestamp.now("UTC").strftime("%Y%m%d_%H%M%S")
    xlsx_path = out_dir / f"{view_name_prefix}__{ts}.xlsx"
    csv_path = out_dir / f"{view_name_prefix}__{ts}.csv"

    # Additional joinable-only outputs
    xlsx_joinable_path = out_dir / f"{view_name_prefix}_joinable__{ts}.xlsx"
    csv_joinable_path = out_dir / f"{view_name_prefix}_joinable__{ts}.csv"

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