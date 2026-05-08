import re
from pathlib import Path

from physprops.util.run_artifacts import utc_stamp, find_tools_root, build_physprops_paths


def test_utc_stamp_format():
    s = utc_stamp()
    assert len(s) == 8 + 1 + 6 + 6 + 1  # YYYYMMDD + T + HHMMSS + ffffff + Z
    assert s[8] == "T"
    assert s[-1] == "Z"
    assert s[:8].isdigit()
    assert s[9:15].isdigit()   # HHMMSS
    assert s[15:21].isdigit()  # microseconds

def test_build_physprops_paths_under_tools_output(tmp_path: Path):
    # Create a fake Tools root marker
    (tmp_path / "Canonical_DB").mkdir()

    # Simulate running from a nested tool folder
    nested = tmp_path / "PhysProps" / "physprops"
    nested.mkdir(parents=True)

    tools_root = find_tools_root(start=nested)
    assert tools_root == tmp_path

    paths = build_physprops_paths("20260101T000000Z", start=nested)

    # Confirm outputs are under Tools/output/physprops/
    for key, p in paths.items():
        # Folder structure
        assert (tmp_path / "output" / "physprops") in p.parents, f"{key} not under Tools/output/physprops: {p}"

        # Filename conventions
        assert p.name.startswith(("wide_physprops_", "legacy_physprops_", "temp_physprops_")), f"Unexpected name: {p.name}"
        assert "20260101T000000Z" in p.name, f"Missing stamp in: {p.name}"