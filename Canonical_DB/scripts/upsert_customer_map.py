from __future__ import annotations

from pathlib import Path
from datetime import datetime, UTC
import shutil
from typing import Optional

import pandas as pd


DB2_XLSX = Path(r"C:\Users\vdevi\AppData\Local\Lysning\Canonical_DB\cas_registry.xlsx")
FEED_CSV = Path(r"Canonical_DB\exports_pipeline\customer_map_feed.csv")
DEFAULT_SHEET = "customer_map"




def utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def upsert_customer_map(
    db2_xlsx: Path,
    feed_csv: Path,
    sheet: str = DEFAULT_SHEET,
    backup: bool = True,
    backup_dir: Optional[Path] = None,
) -> pd.DataFrame:
    """
    Upsert DB2 customer_map sheet from a CSV feed, keeping latest per (customer_id, cas_number_normalized)
    based on timestamp_seen_utc.

    Returns the final customer_map dataframe written.
    """
    db2_xlsx = Path(db2_xlsx)
    feed_csv = Path(feed_csv)

    if not db2_xlsx.exists():
        raise FileNotFoundError(f"DB2 not found: {db2_xlsx}")
    if not feed_csv.exists():
        raise FileNotFoundError(f"Feed CSV not found: {feed_csv.resolve()}")

    # Backup DB2 first (local, safe)
    if backup:
        if backup_dir is None:
            backup_path = db2_xlsx.with_name(f"{db2_xlsx.stem}__backup__{utc_stamp()}.xlsx")
        else:
            backup_dir = Path(backup_dir)
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup_path = backup_dir / f"{db2_xlsx.stem}__backup__{utc_stamp()}.xlsx"
        shutil.copy2(db2_xlsx, backup_path)

    feed = pd.read_csv(feed_csv, dtype=str, keep_default_na=False)

    required = [
        "customer_id",
        "cas_number_normalized",
        "timestamp_seen_utc",
        "Customer Code / Code Unique",
        "Name",
    ]
    missing = [c for c in required if c not in feed.columns]
    if missing:
        raise ValueError(f"Feed missing columns: {missing}. Found: {list(feed.columns)}")

    # Normalize keys gently (do NOT modify Name)
    feed["customer_id"] = feed["customer_id"].astype(str).str.strip()
    feed["cas_number_normalized"] = feed["cas_number_normalized"].astype(str).str.strip()
    feed["timestamp_seen_utc"] = feed["timestamp_seen_utc"].astype(str).str.strip()

    # Read existing customer_map sheet if present; otherwise empty
    try:
        existing = pd.read_excel(db2_xlsx, sheet_name=sheet, engine="openpyxl", dtype=str).fillna("")
    except ValueError:
        existing = pd.DataFrame(columns=feed.columns)

    # Align columns (union)
    all_cols = list(dict.fromkeys(list(existing.columns) + list(feed.columns)))
    existing = existing.reindex(columns=all_cols, fill_value="")
    feed = feed.reindex(columns=all_cols, fill_value="")

    combined = pd.concat([existing, feed], ignore_index=True)
    combined = combined.sort_values("timestamp_seen_utc")
    combined = combined.drop_duplicates(subset=["customer_id", "cas_number_normalized"], keep="last").reset_index(drop=True)

    # Write back only this sheet; preserve other sheets
    with pd.ExcelWriter(db2_xlsx, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
        combined.to_excel(writer, sheet_name=sheet, index=False)

    return combined


def main() -> None:
    # Keep script behavior for your real environment
    DB2_XLSX = Path(r"C:\Users\vdevi\AppData\Local\Lysning\Canonical_DB\cas_registry.xlsx")
    FEED_CSV = Path(r"Canonical_DB\exports_pipeline\customer_map_feed.csv")
    out = upsert_customer_map(DB2_XLSX, FEED_CSV, sheet=DEFAULT_SHEET, backup=True)
    print("Upserted customer_map rows:", len(out))
    print("Wrote customer_map sheet to:", DB2_XLSX)


if __name__ == "__main__":
    main()
