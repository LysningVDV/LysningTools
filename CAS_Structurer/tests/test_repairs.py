import pandas as pd
from cas_structurer.cas_logic import normalize_and_repair_token, build_fixed_cas_cell, build_evidence_indexes

def test_adjacent_swap_auto_fix():
    df = pd.DataFrame([])
    by_code, by_desig = build_evidence_indexes(df)
    cas, status = normalize_and_repair_token("170-41-5", "", "", by_code, by_desig)
    assert cas == "107-41-5"
    assert "fixed swap" in status

def test_missing_check_digit():
    df = pd.DataFrame([])
    by_code, by_desig = build_evidence_indexes(df)
    cas, status = normalize_and_repair_token("1392276-61", "", "", by_code, by_desig)
    assert "fixed checkdigit" in status