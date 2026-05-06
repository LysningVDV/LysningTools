import pandas as pd
from pathlib import Path
from physprops.io.excel_io import export_physprops_wide

def test_export_wide_adds_inchi_key_from_final_inchikey(tmp_path: Path):
    inp = tmp_path / "in.xlsx"
    outp = tmp_path / "wide.xlsx"
    df = pd.DataFrame({"final_inchikey": ["QPFMBZIOSGYJDE-UHFFFAOYSA-N"], "CAS_ID": ["79-00-5"]})
    df.to_excel(inp, index=False, engine="openpyxl")

    export_physprops_wide(str(inp), str(outp), sheet_name=0)
    wide = pd.read_excel(outp, engine="openpyxl")
    assert "inchi_key" in wide.columns
    assert wide["inchi_key"].notna().sum() == 1
    assert wide.loc[0, "inchi_key"] == "QPFMBZIOSGYJDE-UHFFFAOYSA-N"