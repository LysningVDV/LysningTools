import pandas as pd
import pytest

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

def test_split_cas_cell_extra_delimiters():
    val = "64-17-5  /   67-56-1 ;  0-00-0\t107-41-5\n123-45-6"
    toks = split_cas_cell(val)
    assert toks == ["64-17-5", "67-56-1", "0-00-0", "107-41-5", "123-45-6"]

def test_split_cas_cell_embedded_spaces():
    val = "CAS 64-17-5 / CAS 67-56-1"
    toks = split_cas_cell(val)
    assert toks == ["CAS", "64-17-5", "CAS", "67-56-1"]

def test_split_cas_cell_multiple_consecutive_delimiters():
    val = "64-17-5///67-56-1;;0-00-0,,107-41-5"
    toks = split_cas_cell(val)
    assert toks == ["64-17-5", "67-56-1", "0-00-0", "107-41-5"]

def test_split_cas_cell_empty_tokens():
    val = " / ; , 64-17-5 / "
    toks = split_cas_cell(val)
    assert toks == ["64-17-5"]

def test_split_cas_cell_linebreaks_tabs():
    val = "64-17-5\n67-56-1\t0-00-0"
    toks = split_cas_cell(val)
    assert toks == ["64-17-5", "67-56-1", "0-00-0"]

def test_split_cas_cell_unicode_whitespace():
    val = "64-17-5\u00a067-56-1"
    toks = split_cas_cell(val)
    assert toks == ["64-17-5", "67-56-1"]