import pandas as pd

from chem_annotator.io_utils import process_dataframe
from chem_annotator.schema import FEATURE_DEFAULTS


def test_process_dataframe_smoke_valid_invalid_empty_and_dot_salt():
    df = pd.DataFrame(
        [
            {"CAS_ID": "V1", "SMILES": "CCO"},           # valid ethanol
            {"CAS_ID": "I1", "SMILES": "NOT_A_SMILES"},  # invalid parse
            {"CAS_ID": "E1", "SMILES": None},            # empty after cleaning
            {"CAS_ID": "D1", "SMILES": "CCO.[Na+]"},     # dot/salt -> clean_smiles keeps CCO
        ]
    )

    out_df, invalid, df_empty = process_dataframe(df)

    schema_keys = list(FEATURE_DEFAULTS.keys())

    # 1) Out df must contain schema columns (full schema for all rows)
    for k in schema_keys:
        assert k in out_df.columns, f"Missing schema column in output dataframe: {k}"

    # 2) Row-wise checks by CAS_ID
    by_id = {row["CAS_ID"]: row for row in out_df.to_dict(orient="records")}

    # Valid ethanol
    assert by_id["V1"]["Valid"] == 1
    assert by_id["V1"]["TotalAlcoholCount"] >= 1

    # Dot/salt ethanol
    assert by_id["D1"]["Valid"] == 1
    assert by_id["D1"]["TotalAlcoholCount"] >= 1

    # Invalid parse: must match canonical defaults exactly
    assert by_id["I1"]["Valid"] == 0
    for k, default_v in FEATURE_DEFAULTS.items():
        assert by_id["I1"][k] == default_v, f"Invalid row expected {k}={default_v!r}, got {by_id['I1'][k]!r}"

    # Empty-after-clean: must match canonical defaults exactly
    assert by_id["E1"]["Valid"] == 0
    for k, default_v in FEATURE_DEFAULTS.items():
        assert by_id["E1"][k] == default_v, f"Empty row expected {k}={default_v!r}, got {by_id['E1'][k]!r}"

    # 3) invalid list and df_empty reports should capture the right rows
    assert any(r.get("CAS_ID") == "I1" and r.get("Reason") == "Failed to parse" for r in invalid)
    assert not df_empty.empty
    assert any(r.get("CAS_ID") == "E1" and r.get("Reason") == "Empty after cleaning" for r in df_empty.to_dict(orient="records"))