import json
from pathlib import Path
import pandas as pd
from canonical_common.cas_view_export import export_cas_view
import pytest

pytestmark=pytest.mark.integration


def test_export_cas_view_adds_customer_overlay(tmp_path: Path):
    # --- Create temp DB1 canonical file ---
    db1 = tmp_path / "canonical_physchemprops.xlsx"
    db1_df = pd.DataFrame(
        [
            {"inchi_key": "AAAAAAAAAAAAAA-UHFFFAOYSA-N", "computed_mw": 46.0},
        ]
    )
    with pd.ExcelWriter(db1, engine="openpyxl") as w:
        db1_df.to_excel(w, sheet_name="canonical", index=False)

    # --- Create temp DB2 cas_registry.xlsx with registry + customer_map ---
    db2 = tmp_path / "cas_registry.xlsx"
    reg = pd.DataFrame(
        [
            {
                "cas_number_normalized": "64-17-5",
                "inchi_key": "AAAAAAAAAAAAAA-UHFFFAOYSA-N",
                "cas_status": "valid",
            },
            {
                "cas_number_normalized": "7732-18-5",
                "inchi_key": "",
                "cas_status": "valid",
            },
        ]
    )
    cmap = pd.DataFrame(
        [
            {
                "customer_id": "MANE",
                "cas_number_normalized": "64-17-5",
                "Customer Code / Code Unique": "A01016",
                "Name": "ETHANOL",
                "timestamp_seen_utc": "2026-05-08T00:00:00+00:00",
                "cas_validity": "valid",
            }
        ]
    )
    with pd.ExcelWriter(db2, engine="openpyxl") as w:
        reg.to_excel(w, sheet_name="registry", index=False)
        cmap.to_excel(w, sheet_name="customer_map", index=False)

    # --- Minimal DB2 schema json for allowlist loader ---
    schema = tmp_path / "cas_registry_schema.json"
    schema_payload = {
        "allowlist": list(dict.fromkeys(list(reg.columns) + ["Customer Code / Code Unique", "Name"]))
    }
    schema.write_text(json.dumps(schema_payload), encoding="utf-8")

    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)

    result = export_cas_view(
        db1_xlsx=db1,
        db2_xlsx=db2,
        db2_schema_json=schema,
        out_dir=out_dir,
        view_name_prefix="cas_view",
        customer_id="MANE",
    )

    out_csv = Path(result["csv"])
    assert out_csv.exists()

    df_out = pd.read_csv(out_csv, dtype=str, keep_default_na=False)

    assert "Customer Code / Code Unique" in df_out.columns
    assert "Name" in df_out.columns

    ethanol = df_out[df_out["cas_number_normalized"] == "64-17-5"].iloc[0]
    assert ethanol["Customer Code / Code Unique"] == "A01016"
    assert ethanol["Name"] == "ETHANOL"
