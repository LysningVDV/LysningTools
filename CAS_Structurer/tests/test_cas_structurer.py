import pandas as pd

from cas_structurer.cas_logic import (
    split_cas_cell,
    is_valid_cas,
    normalize_and_repair_token,
    build_fixed_cas_cell,
    build_evidence_indexes,
)

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def make_evidence_df(rows):
    """
    Utility to build a minimal dataframe for evidence-based tests.
    rows: list of dicts with keys CAS, Code Unique, Designation
    """
    return pd.DataFrame(rows)


# ------------------------------------------------------------------
# Basic CAS validation
# ------------------------------------------------------------------

def test_is_valid_cas_basic():
    assert is_valid_cas("64-17-5")      # ethanol
    assert is_valid_cas("107-41-5")
    assert not is_valid_cas("170-41-5") # checksum invalid
    assert not is_valid_cas("0-00-0")
    assert not is_valid_cas("12345")


# ------------------------------------------------------------------
# CAS splitting
# ------------------------------------------------------------------

def test_split_cas_cell_multiple_delimiters():
    val = "64-17-5 / 67-56-1; 0-00-0\n107-41-5"
    toks = split_cas_cell(val)
    assert toks == ["64-17-5", "67-56-1", "0-00-0", "107-41-5"]


def test_split_excel_date_object():
    ts = pd.Timestamp("2656-10-07")
    toks = split_cas_cell(ts)
    assert toks == ["2656-10-07"]


# ------------------------------------------------------------------
# Adjacent swap logic
# ------------------------------------------------------------------

def test_adjacent_swap_unique_auto_fix():
    """
    170-41-5 has exactly one adjacent swap that is valid: 107-41-5
    This should auto-fix WITHOUT requiring evidence.
    """
    df = make_evidence_df([])
    by_code, by_desig = build_evidence_indexes(df)

    cas, status = normalize_and_repair_token(
        "170-41-5",
        code="X1",
        desig="Anything",
        by_code=by_code,
        by_desig=by_desig,
    )

    assert cas == "107-41-5"
    assert "fixed swap" in status


# ------------------------------------------------------------------
# Missing check digit
# ------------------------------------------------------------------

def test_missing_check_digit_fix():
    df = make_evidence_df([])
    by_code, by_desig = build_evidence_indexes(df)

    cas, status = normalize_and_repair_token(
        "1392276-61",
        code="X2",
        desig="Test",
        by_code=by_code,
        by_desig=by_desig,
    )

    assert is_valid_cas(cas)
    assert "fixed checkdigit" in status


# ------------------------------------------------------------------
# Excel date artifact + suggestions
# ------------------------------------------------------------------

def test_excel_date_artifact_suggestions():
    """
    2656-10-07 is date-like.
    It should NOT auto-fix, but SHOULD produce suggestions
    via date-edit + adjacent-key logic.
    """
    df = make_evidence_df([])
    by_code, by_desig = build_evidence_indexes(df)

    cas, status = normalize_and_repair_token(
        "2656-10-07",
        code="X3",
        desig="Corps Jacinthe",
        by_code=by_code,
        by_desig=by_desig,
    )

    assert cas == "2656-10-07"
    assert "suggestions" in status
    assert "via" in status


# ------------------------------------------------------------------
# Evidence-based fixing
# ------------------------------------------------------------------

def test_evidence_based_fix_by_designation():
    """
    If a valid CAS exists elsewhere with the same Designation,
    the typo version should be auto-fixed.
    """
    df = make_evidence_df([
        {"CAS": "107-41-5", "Code Unique": "A1", "Designation": "KnownMaterial"},
    ])
    by_code, by_desig = build_evidence_indexes(df)

    cas, status = normalize_and_repair_token(
        "170-41-5",
        code="A2",
        desig="KnownMaterial",
        by_code=by_code,
        by_desig=by_desig,
    )

    assert cas == "107-41-5"
    assert "fixed swap" in status or "fixed" in status


# ------------------------------------------------------------------
# Numpad adjacency
# ------------------------------------------------------------------

def test_numpad_adjacent_digit_fix():
    """
    5 is adjacent to 2/4/6/8 on numpad.
    This test only checks that logic runs and suggestions/fixes appear.
    """
    df = make_evidence_df([])
    by_code, by_desig = build_evidence_indexes(df)

    cas, status = normalize_and_repair_token(
        "245-57-1",
        code="X4",
        desig="AdjTest",
        by_code=by_code,
        by_desig=by_desig,
    )

    # Might not auto-fix, but should not crash and may suggest
    assert cas == "245-57-1"
    assert "invalid" in status


# ------------------------------------------------------------------
# FixedCAS full-cell reconstruction
# ------------------------------------------------------------------

def test_build_fixed_cas_cell():
    df = make_evidence_df([])
    by_code, by_desig = build_evidence_indexes(df)

    fixed = build_fixed_cas_cell(
        "64-17-5 / 0-00-0 / 170-41-5 / 12345",
        code="X5",
        desig="Mix",
        by_code=by_code,
        by_desig=by_desig,
    )

    # 0-00-0 removed
    assert "0-00-0" not in fixed

    # valid stays
    assert "64-17-5" in fixed

    # fixed swap applied
    assert "107-41-5" in fixed

    # invalid retained and marked
    assert "12345 (invalid)" in fixed