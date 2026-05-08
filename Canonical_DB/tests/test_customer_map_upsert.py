from pathlib import Path
import pandas as pd
import pytest

from Canonical_DB.scripts.upsert_customer_map import upsert_customer_map

pytestmark=pytest.mark.integration

def test_customer_map_upsert_latest_wins(tmp_path: Path):
    # Arrange: create a fake DB2 workbook with an existing customer_map sheet
    db2 = tmp_path / "cas_registry.xlsx"
    existing = pd.DataFrame([
        {
            "customer_id": "MANE",
            "cas_number_normalized": "64-17-5",
            "timestamp_seen_utc": "2026-05-08T00:00:00+00:00",
            "Customer Code / Code Unique": "OLD1",
            "Name": "OLD NAME",
            "cas_validity": "valid",
        }
    ])

    # Also create a dummy registry sheet to mimic real DB2 (not used by upsert)
    registry = pd.DataFrame([{"cas_number_normalized": "64-17-5", "inchi_key": "X"}])

    with pd.ExcelWriter(db2, engine="openpyxl") as w:
        registry.to_excel(w, sheet_name="registry", index=False)
        existing.to_excel(w, sheet_name="customer_map", index=False)

    # Feed has same key but newer timestamp -> should overwrite code/name
    feed = pd.DataFrame([
        {
            "customer_id": "MANE",
            "cas_number_normalized": "64-17-5",
            "timestamp_seen_utc": "2026-05-09T00:00:00+00:00",
            "Customer Code / Code Unique": "NEW1",
            "Name": "NEW NAME",
            "cas_validity": "valid",
        }
    ])
    feed_csv = tmp_path / "customer_map_feed.csv"
    feed.to_csv(feed_csv, index=False, encoding="utf-8")

    # Act
    out = upsert_customer_map(db2, feed_csv, backup=False)

    # Assert: latest wins
    assert len(out) == 1
    row = out.iloc[0].to_dict()
    assert row["Customer Code / Code Unique"] == "NEW1"
    assert row["Name"] == "NEW NAME"

    # Also confirm it's actually written back into the workbook
    read_back = pd.read_excel(db2, sheet_name="customer_map", engine="openpyxl", dtype=str).fillna("")
    assert read_back.iloc[0]["Customer Code / Code Unique"] == "NEW1"
    assert read_back.iloc[0]["Name"] == "NEW NAME"