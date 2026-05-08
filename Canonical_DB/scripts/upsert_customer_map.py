
from pathlib import Path
import pandas as pd
from datetime import datetime, UTC
import shutil


DB2_XLSX = Path(r"C:\Users\vdevi\AppData\Local\Lysning\Canonical_DB\cas_registry.xlsx")
FEED_CSV = Path(r"Canonical_DB\exports_pipeline\customer_map_feed.csv")
SHEET = "customer_map"



def utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def main() -> None:
    if not DB2_XLSX.exists():
        raise FileNotFoundError(f"DB2 not found: {DB2_XLSX}")
    if not FEED_CSV.exists():
        raise FileNotFoundError(f"Feed CSV not found: {FEED_CSV.resolve()}")

    # Backup DB2 first (local, safe)
    backup = DB2_XLSX.with_name(f"cas_registry__backup__{utc_stamp()}.xlsx")
    shutil.copy2(DB2_XLSX, backup)
    print("Backup written:", backup)

    # Read feed
    feed = pd.read_csv(FEED_CSV, dtype=str, keep_default_na=False)
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

    # Normalize key columns gently (do NOT modify Name)
    feed["customer_id"] = feed["customer_id"].astype(str).str.strip()
    feed["cas_number_normalized"] = feed["cas_number_normalized"].astype(str).str.strip()
    feed["timestamp_seen_utc"] = feed["timestamp_seen_utc"].astype(str).str.strip()

    # Read existing sheet if present; else create empty with feed columns
    try:
        existing = pd.read_excel(DB2_XLSX, sheet_name=SHEET, engine="openpyxl", dtype=str)
        existing = existing.fillna("")
        print("Existing customer_map rows:", len(existing))
    except ValueError:
        existing = pd.DataFrame(columns=feed.columns)
        print("No existing customer_map sheet; creating new.")

    # Align columns (union)
    all_cols = list(dict.fromkeys(list(existing.columns) + list(feed.columns)))
    existing = existing.reindex(columns=all_cols, fill_value="")
    feed = feed.reindex(columns=all_cols, fill_value="")

    # Combine and keep latest per (customer_id, cas_number_normalized)
    combined = pd.concat([existing, feed], ignore_index=True)
    combined = combined.sort_values("timestamp_seen_utc")
    combined = combined.drop_duplicates(
        subset=["customer_id", "cas_number_normalized"],
        keep="last",
    ).reset_index(drop=True)

    print("Upserted customer_map rows:", len(combined))

    # Write back only this sheet; preserve other sheets
    with pd.ExcelWriter(DB2_XLSX, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
        combined.to_excel(writer, sheet_name=SHEET, index=False)

    print("Wrote customer_map sheet to:", DB2_XLSX)


if __name__ == "__main__":
    main()
