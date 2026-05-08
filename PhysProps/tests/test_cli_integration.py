import sys
from pathlib import Path

import pandas as pd

from physprops.util.run_artifacts import find_tools_root


def _write_xlsx(df: pd.DataFrame, path: Path) -> None:
    df.to_excel(path, index=False, engine="openpyxl")


def _physprops_outdir_from_main_module(main_module) -> Path:
    """
    Resolve Tools/output/physprops exactly the way runtime does:
    starting from the installed source file location of physprops.main.
    """
    tools_root = find_tools_root(start=Path(main_module.__file__).resolve())
    return tools_root / "output" / "physprops"


def test_cli_creates_legacy_wide_and_attempts_canonical(tmp_path: Path, monkeypatch):
    # Import INSIDE test to avoid import-time side effects during pytest collection
    import physprops.main as main

    # Input
    in_path = tmp_path / "input.xlsx"
    _write_xlsx(pd.DataFrame({"AnyIdentifier": ["A"]}), in_path)

    # Legacy output is explicit CLI argument -> should be written exactly here
    out_path = tmp_path / "output_cas_results.xlsx"

    # Use a valid-format InChIKey so canonical validation won't drop it
    ik = "AAAAAAAAAAAAAA-UHFFFAOYSA-N"

    legacy_df = pd.DataFrame({"inchi_key": [ik], "legacy_col": [1]})
    wide_df = pd.DataFrame({"inchi_key": [ik], "wide_col": [2]})

    def fake_resolve(df, return_wide=False):
        assert return_wide is True
        return legacy_df, wide_df

    monkeypatch.setattr(main, "resolve_dataframe", fake_resolve)

    # Prevent touching your real canonical DB:
    called = {}

    def fake_read_xlsx(path, sheet_name=0):
        called["canonical_db_path"] = str(path)
        return pd.DataFrame({"inchi_key": []})

    monkeypatch.setattr(main, "read_xlsx", fake_read_xlsx)

    # Run CLI
    monkeypatch.setattr(sys, "argv", ["physprops", str(in_path), str(out_path), "--log", "INFO"])
    main.cli()

    # Legacy output: explicit output path must exist (not timestamped anymore)
    assert out_path.exists(), f"Legacy output missing at explicit path: {out_path}"

    # Wide output: should be under Tools/output/physprops with new naming convention
    outdir = _physprops_outdir_from_main_module(main)
    wide_files = list(outdir.glob("wide_physprops_*.xlsx"))
    assert len(wide_files) >= 1, f"No wide export found in {outdir}. Found: {wide_files}"

    # Temp wide source: should also exist (regression guard)
    temp_files = list(outdir.glob("temp_physprops_*__out_wide_source.xlsx"))
    assert len(temp_files) >= 1, f"No temp wide source found in {outdir}. Found: {temp_files}"

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

    # Avoid canonical reads
    monkeypatch.setattr(main, "read_xlsx", lambda path, sheet_name=0: pd.DataFrame({"inchi_key": []}))

    outdir = _physprops_outdir_from_main_module(main)
    outdir.mkdir(parents=True, exist_ok=True)

    # Record current wide exports (important if output dir isn't isolated across tests)
    before = set(p.resolve() for p in outdir.glob("wide_physprops_*.xlsx"))

    # Run twice
    monkeypatch.setattr(sys, "argv", ["physprops", str(in_path), str(out_path), "--log", "INFO"])
    main.cli()
    monkeypatch.setattr(sys, "argv", ["physprops", str(in_path), str(out_path), "--log", "INFO"])
    main.cli()

    after = set(p.resolve() for p in outdir.glob("wide_physprops_*.xlsx"))
    created = after - before

    # Expect at least +2 new wide files (timestamped per run).
    # (If two runs happen inside the same second, safe_output_path may suffix, still counts as two.)
    assert len(created) >= 2, (
        "Expected at least 2 new wide exports after two runs. "
        f"Before={len(before)} After={len(after)} New={len(created)} Outdir={outdir}"
    )

    # Legacy output: explicit output path should exist (written/overwritten)
    assert out_path.exists(), f"Legacy output missing at explicit path: {out_path}"