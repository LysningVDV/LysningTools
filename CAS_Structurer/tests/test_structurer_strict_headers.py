from pathlib import Path
import pandas as pd
import pytest
from cas_structurer.io_excel import process_file


def test_structurer_strict_missing_header_errors(tmp_path: Path):
    inp = tmp_path / "input.xlsx"
    df = pd.DataFrame({"CAS_ID": ["64-17-5"], "ING_ID": ["A1"], "Name": ["ETHANOL"]})
    df.to_excel(inp, index=False, engine="openpyxl")

    with pytest.raises(ValueError) as e:
        process_file(
            input_path=inp,
            sheet=None,
            outdir=tmp_path,
            customer_id="MANE",
            cas_col="CAS_ID",
            code_col="ING_ID",
            name_col="NAME",  # wrong capitalization
            strict=True,
        )

    msg = str(e.value)
    assert "Missing required columns" in msg
    assert "Found columns" in msg

def test_structurer_accepts_custom_headers_strict(tmp_path: Path):
    inp = tmp_path / "input.xlsx"
    df = pd.DataFrame(
        {
            "CAS_ID": ["64-17-5; 67-56-1", "7732-18-5"],
            "ING_ID": ["A1", "A2"],
            "Name": ["ETHANOL MIX", "WATER"],
        }
    )
    df.to_excel(inp, index=False, engine="openpyxl")

    outdir = tmp_path / "out"
    out1, out2, manifest = process_file(
        input_path=inp,
        sheet=None,
        outdir=outdir,
        customer_id="MANE",
        cas_col="CAS_ID",
        code_col="ING_ID",
        name_col="Name",
        strict=True,
    )

    assert out1.exists()
    assert out2.exists()
    assert manifest.exists()

    exploded = pd.read_excel(out1, engine="openpyxl")
    assert "customer_id" in exploded.columns
    assert "timestamp_seen_utc" in exploded.columns
    assert "Customer Code / Code Unique" in exploded.columns
    assert "Name" in exploded.columns
    assert "CAS" in exploded.columns
    assert "CAS_valid" in exploded.columns