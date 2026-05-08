import sys
from pathlib import Path
import pytest
import pandas as pd

from physprops.util.run_artifacts import find_tools_root


def _write_xlsx(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(path, index=False, engine="openpyxl")


def _physprops_outdirs() -> dict:
    """
    Resolve Tools/output/physprops the same way runtime does: via Tools root detection.
    """
    tools_root = find_tools_root(start=Path(__file__).resolve())
    phys_out = tools_root / "output" / "physprops"
    legacy_dir = phys_out / "legacy"
    phys_out.mkdir(parents=True, exist_ok=True)
    legacy_dir.mkdir(parents=True, exist_ok=True)
    return {"tools_root": tools_root, "phys_out": phys_out, "legacy_dir": legacy_dir}


def _snapshot_outputs(phys_out: Path, legacy_dir: Path) -> dict:
    return {
        "wide": set(p.resolve() for p in phys_out.glob("wide_physprops_*.xlsx")),
        "temp": set(p.resolve() for p in phys_out.glob("temp_physprops_*__out_wide_source.xlsx")),
        "legacy": set(p.resolve() for p in legacy_dir.glob("legacy_physprops_*.xlsx")),
    }


def test_cli_creates_legacy_wide_and_attempts_canonical(tmp_path: Path, monkeypatch):
    # Import INSIDE test to avoid import-time side effects during pytest collection
    import physprops.main as main

    # Input file (content irrelevant because we monkeypatch resolve_dataframe)
    in_path = tmp_path / "input.xlsx"
    _write_xlsx(pd.DataFrame({"AnyIdentifier": ["A"]}), in_path)

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

    # main.py historically used read_xlsx for canonical reads; patch if present
    if hasattr(main, "read_xlsx"):
        monkeypatch.setattr(main, "read_xlsx", fake_read_xlsx)

    # Snapshot standardized output folders before running
    outdirs = _physprops_outdirs()
    before = _snapshot_outputs(outdirs["phys_out"], outdirs["legacy_dir"])

    # Run CLI in Option 2B mode: provide ONLY input (output_excel is optional/ignored)
    monkeypatch.setattr(sys, "argv", ["physprops", str(in_path), "--log", "INFO"])
    main.cli()

    # Snapshot after
    after = _snapshot_outputs(outdirs["phys_out"], outdirs["legacy_dir"])

    # Wide output: should be under Tools/output/physprops with naming convention
    new_wide = after["wide"] - before["wide"]
    assert len(new_wide) >= 1, f"No new wide export found in {outdirs['phys_out']}. Before={len(before['wide'])} After={len(after['wide'])}"

    # Temp wide source: should also exist (regression guard)
    new_temp = after["temp"] - before["temp"]
    assert len(new_temp) >= 1, f"No new temp wide source found in {outdirs['phys_out']}. Before={len(before['temp'])} After={len(after['temp'])}"

    # Standardized legacy: must exist under Tools/output/physprops/legacy/
    new_legacy = after["legacy"] - before["legacy"]
    assert len(new_legacy) >= 1, f"No new standardized legacy export found in {outdirs['legacy_dir']}. Before={len(before['legacy'])} After={len(after['legacy'])}"

    # Canonical path should have been attempted (if the code path uses read_xlsx)
    if hasattr(main, "read_xlsx"):
        assert "canonical_db_path" in called
        assert called["canonical_db_path"].endswith("canonical_physchemprops.xlsx")


def test_cli_wide_not_overwritten_two_runs(tmp_path: Path, monkeypatch):
    import physprops.main as main

    in_path = tmp_path / "input.xlsx"
    _write_xlsx(pd.DataFrame({"AnyIdentifier": ["A"]}), in_path)

    ik = "BBBBBBBBBBBBBB-UHFFFAOYSA-N"
    legacy_df = pd.DataFrame({"inchi_key": [ik], "legacy_col": [1]})
    wide_df = pd.DataFrame({"inchi_key": [ik], "wide_col": [2]})

    def fake_resolve(df, return_wide=False):
        assert return_wide is True
        return legacy_df, wide_df

    monkeypatch.setattr(main, "resolve_dataframe", fake_resolve)

    # Avoid canonical reads if present
    if hasattr(main, "read_xlsx"):
        monkeypatch.setattr(main, "read_xlsx", lambda path, sheet_name=0: pd.DataFrame({"inchi_key": []}))

    outdirs = _physprops_outdirs()
    before = _snapshot_outputs(outdirs["phys_out"], outdirs["legacy_dir"])

    # Run twice (Option 2B: input only)
    monkeypatch.setattr(sys, "argv", ["physprops", str(in_path), "--log", "INFO"])
    main.cli()

    monkeypatch.setattr(sys, "argv", ["physprops", str(in_path), "--log", "INFO"])
    main.cli()

    after = _snapshot_outputs(outdirs["phys_out"], outdirs["legacy_dir"])

    created_wide = after["wide"] - before["wide"]
    created_temp = after["temp"] - before["temp"]
    created_legacy = after["legacy"] - before["legacy"]

    # Expect at least +2 new files of each kind (timestamped per run).
    assert len(created_wide) >= 2, (
        "Expected at least 2 new wide exports after two runs. "
        f"Before={len(before['wide'])} After={len(after['wide'])} New={len(created_wide)} Outdir={outdirs['phys_out']}"
    )
    assert len(created_temp) >= 2, (
        "Expected at least 2 new temp wide-source exports after two runs. "
        f"Before={len(before['temp'])} After={len(after['temp'])} New={len(created_temp)} Outdir={outdirs['phys_out']}"
    )
    assert len(created_legacy) >= 2, (
        "Expected at least 2 new standardized legacy exports after two runs. "
        f"Before={len(before['legacy'])} After={len(after['legacy'])} New={len(created_legacy)} Outdir={outdirs['legacy_dir']}"
    )
