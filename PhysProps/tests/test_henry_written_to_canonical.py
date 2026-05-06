from pathlib import Path
import pandas as pd
import shutil
import os

def test_henry_columns_present_and_nonnull_in_canonical_db(tmp_path):    
    db_root = os.environ.get("CANONICAL_DB_LOCAL_ROOT")
    if db_root:
        canonical_db = Path(db_root) / "canonical_physchemprops.xlsx"
    else:
        canonical_db = Path(r"C:\Users\vdevi\OneDrive - Lysning Innovation Consultants B.V\Lysning\Tools\Canonical_DB\canonical_physchemprops.xlsx")
    print("[TEST] canonical_db =", canonical_db, "size =", canonical_db.stat().st_size)
    assert canonical_db.exists(), f"Canonical DB not found: {canonical_db}"

    local_copy = tmp_path / "canonical_physchemprops_copy.xlsx"
    shutil.copy2(canonical_db, local_copy)

    src_size = canonical_db.stat().st_size
    if src_size < 50_000:
        print(f"[WARN] canonical DB source is small ({src_size} bytes) — OneDrive may be interfering")

    df = pd.read_excel(local_copy, engine="openpyxl")
    df.columns = [str(c).strip() for c in df.columns]  # also normalizes any whitespace

    cols = [
        "henry_constant_mol_m3_Pa_25C",
        "log_henry_constant_mol_m3_Pa_25C",
        "source_henry_constant",
    ]
    missing = [c for c in cols if c not in df.columns]


    assert not missing, f"Missing expected Henry columns in canonical DB: {missing}"

    nonnull = {c: int(df[c].notna().sum()) for c in cols}
    assert nonnull["henry_constant_mol_m3_Pa_25C"] > 0, f"No Henry values written. nonnull={nonnull}"
    assert nonnull["source_henry_constant"] > 0, f"No Henry source written. nonnull={nonnull}"
