import os
from pathlib import Path
from physprops.io.excel_io import export_physprops_wide

def test_export_physprops_wide_writes_file_and_returns_none(tmp_path: Path):
    # create minimal input file
    import pandas as pd
    inp = tmp_path / "in.xlsx"
    outp = tmp_path / "wide.xlsx"
    pd.DataFrame({"CAS_ID": ["64-17-5"]}).to_excel(inp, index=False, engine="openpyxl")

    r = export_physprops_wide(str(inp), str(outp), sheet_name=0)
    assert r is None
    assert outp.exists()
    assert os.path.getsize(outp) > 0