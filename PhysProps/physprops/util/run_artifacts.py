
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

import pandas as pd


def utc_stamp() -> str:
    # Collision-proof UTC stamp
    return pd.Timestamp.now("UTC").strftime("%Y%m%dT%H%M%S%fZ")



def find_tools_root(start: Path | None = None, max_hops: int = 12) -> Path:
    """
    Walk upward from `start` (or cwd) until a folder containing 'Canonical_DB' exists.
    This keeps tools runnable from subfolders while producing outputs in a shared repo root.
    """
    cur = (start or Path.cwd()).resolve()
    for _ in range(max_hops):
        if (cur / "Canonical_DB").exists():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return (start or Path.cwd()).resolve()


def physprops_output_dir(start: Path | None = None) -> Path:
    tools_root = find_tools_root(start=start)
    out_dir = tools_root / "output" / "physprops"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def build_physprops_paths(run_stamp: str, start: Path | None = None) -> Dict[str, Path]:
    """
    Returns standard run artifact paths for PhysProps.
    Keys are stable role names for logging/manifest.
    """
    out_dir = physprops_output_dir(start=start)
    return {
        "wide": out_dir / f"wide_physprops_{run_stamp}.xlsx",
        "legacy_default": out_dir / f"legacy_physprops_{run_stamp}.xlsx",
        "temp_out_wide_source": out_dir / f"temp_physprops_{run_stamp}__out_wide_source.xlsx",
    }