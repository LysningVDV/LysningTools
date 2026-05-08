import json
import subprocess
import sys
import time  
from pathlib import Path
import pandas as pd
from physprops.util.run_artifacts import find_tools_root

def test_inchikey_only_input_works(tmp_path):
    inp = tmp_path / "inchikey_only.xlsx"
    pd.DataFrame({"InChIKey": ["NTPLXRHDUXRPNE-UHFFFAOYSA-N"]}).to_excel(inp, index=False)

    tools_root = find_tools_root(start=Path(__file__).resolve())
    legacy_dir = tools_root / "output" / "physprops" / "legacy"
    legacy_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()

    # Option 2B: output_excel is optional; do not pass it
    subprocess.check_call([sys.executable, "-m", "physprops.main", str(inp), "--log", "INFO"])

    candidates = list(legacy_dir.glob("legacy_physprops_*.xlsx"))
    assert candidates, f"No standardized legacy files found in {legacy_dir}"

    newest = max(candidates, key=lambda p: p.stat().st_mtime)
    assert newest.stat().st_mtime >= t0, f"No new legacy file created in {legacy_dir}. Newest is {newest}"
