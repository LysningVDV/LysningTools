import sys
from pathlib import Path

import pandas as pd


def _write_xlsx(df: pd.DataFrame, path: Path) -> None:
    df.to_excel(path, index=False, engine="openpyxl")


def test_cli_creates_legacy_wide_and_attempts_canonical(tmp_path: Path, monkeypatch):
    # Import INSIDE test to avoid import-time side effects during pytest collection
    import physprops.main as main

    # Input
    in_path = tmp_path / "input.xlsx"
    _write_xlsx(pd.DataFrame({"AnyIdentifier": ["A"]}), in_path)

    # Legacy output base
    out_path = tmp_path / "output_cas_results.xlsx"

    # Use a valid-format InChIKey so canonical validation won't drop it
    ik = "AAAAAAAAAAAAAA-UHFFFAOYSA-N"

    legacy_df = pd.DataFrame({"inchi_key": [ik], "legacy_col": [1]})
    wide_df = pd.DataFrame({"inchi_key": [ik], "wide_col": [2]})

    def fake_resolve(df, return_wide=False):
        assert return_wide is True
        return legacy_df, wide_df

    monkeypatch.setattr(main, "resolve_dataframe", fake_resolve)

    # Prevent touching your real OneDrive canonical DB:
    called = {}

    def fake_read_xlsx(path, sheet_name=0):
        called["canonical_db_path"] = str(path)
        return pd.DataFrame({"inchi_key": []})

    monkeypatch.setattr(main, "read_xlsx", fake_read_xlsx)

    # Run CLI
    monkeypatch.setattr(sys, "argv", ["physprops", str(in_path), str(out_path), "--log", "INFO"])
    main.cli()

    # Outputs should exist (timestamped variants)
    assert len(list(tmp_path.glob("output_cas_results__*.xlsx"))) == 1
    assert len(list(tmp_path.glob("physprops_export_wide__*.xlsx"))) == 1

    # Canonical path should have been attempted
    assert "canonical_db_path" in called
    assert called["canonical_db_path"].endswith("canonical_physchemprops.xlsx")


def test_cli_wide_not_overwritten_two_runs(tmp_path: Path, monkeypatch):
    import physprops.main as main

    in_path = tmp_path / "input.xlsx"
    _write_xlsx(pd.DataFrame({"AnyIdentifier": ["A"]}), in_path)

    out_path = tmp_path / "output_cas_results.xlsx"

    ik = "BBBBBBBBBBBBBB-UHFFFAOYSA-N"

    legacy_df = pd.DataFrame({"inchi_key": [ik], "legacy_col": [1]})
    wide_df = pd.DataFrame({"inchi_key": [ik], "wide_col": [2]})

    def fake_resolve(df, return_wide=False):
        assert return_wide is True
        return legacy_df, wide_df

    monkeypatch.setattr(main, "resolve_dataframe", fake_resolve)

    # Avoid OneDrive canonical reads
    monkeypatch.setattr(main, "read_xlsx", lambda path, sheet_name=0: pd.DataFrame({"inchi_key": []}))

    # Run twice
    monkeypatch.setattr(sys, "argv", ["physprops", str(in_path), str(out_path), "--log", "INFO"])
    main.cli()
    monkeypatch.setattr(sys, "argv", ["physprops", str(in_path), str(out_path), "--log", "INFO"])
    main.cli()

    assert len(list(tmp_path.glob("output_cas_results__*.xlsx"))) == 2
    assert len(list(tmp_path.glob("physprops_export_wide__*.xlsx"))) == 2