import pandas as pd


def test_save_load_roundtrip(tmp_path):
    import physprops.io.excel_io as excel_io

    df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    path = tmp_path / "roundtrip.xlsx"

    excel_io.save_excel(df, str(path))
    got = excel_io.load_excel(str(path), sheet_name=None)

    # Ensure content preserved
    assert list(got.columns) == ["a", "b"]
    assert got.shape == (2, 2)
