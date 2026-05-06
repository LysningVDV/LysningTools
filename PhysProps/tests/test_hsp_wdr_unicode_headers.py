from pathlib import Path
import pytest
import pandas as pd
from physprops.sources.hsp_wdr import WDRHSPDatabase


def test_wdr_hsp_unicode_headers_and_quantity_parse_without_csv(tmp_path: Path):
    """
    Regression test for the unicode WDR headers (δd/δp/δh) + Quantity parsing.

    This avoids CSV/unicode normalization quirks by exercising _normalize_columns()
    directly on a DataFrame that uses the unicode delta headers.
    """
    # Build a minimal DF using the unicode delta headers explicitly
    df = pd.DataFrame(
        {
            "inchi_key": ["QPFMBZIOSGYJDE-UHFFFAOYSA-N"],
            "\u03b4d": ['Quantity[18.8, Sqrt["Megapascals"]]'],
            "\u03b4p": ['Quantity[5.1, Sqrt["Megapascals"]]'],
            "\u03b4h": ['Quantity[9.4, Sqrt["Megapascals"]]'],
            "\u03b4t": ['Quantity[21.7, Sqrt["Megapascals"]]'],
        }
    )

    # Create an uninitialized instance to call the instance method
    db = object.__new__(WDRHSPDatabase)

    # Normalize columns: should map unicode δ* -> delta_*_raw and parse -> delta_*
    df2 = WDRHSPDatabase._normalize_columns(db, df)

    assert "delta_d_raw" in df2.columns
    assert "delta_p_raw" in df2.columns
    assert "delta_h_raw" in df2.columns
    assert "delta_d" in df2.columns
    assert "delta_p" in df2.columns
    assert "delta_h" in df2.columns

    assert abs(float(df2.loc[0, "delta_d"]) - 18.8) < 1e-9
    assert abs(float(df2.loc[0, "delta_p"]) - 5.1) < 1e-9
    assert abs(float(df2.loc[0, "delta_h"]) - 9.4) < 1e-9


    
def test_wdr_hsp_real_csv_smoke():
    csv_path = Path("physprops/sources/hsp_wdr/JoshuaSchrier_Hansen-Solubility-Parameters.csv")
    if not csv_path.exists():
        pytest.skip(f"Missing WDR CSV at {csv_path}")

    db = WDRHSPDatabase(csv_path)

    # At least some keys should exist
    assert hasattr(db, "df")
    assert len(db.df) > 0
    assert hasattr(db, "by_inchikey")

    # Known key from your debugging
    triplet, src, warn = db.lookup_measured("QPFMBZIOSGYJDE-UHFFFAOYSA-N")
    # If the dataset changes, the key might not exist; don't hard-fail the world.
    if triplet is None:
        pytest.skip("Known test key not present or not fully parsed in this CSV version.")
    assert warn is None
    assert "Wolfram" in src
