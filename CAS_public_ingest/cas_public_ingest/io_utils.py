from __future__ import annotations

import json
import os
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def to_plain_dict(obj: Any) -> Dict[str, Any]:
    if is_dataclass(obj):
        return asdict(obj)
    if isinstance(obj, dict):
        return obj
    raise TypeError(f"Unsupported object type for to_plain_dict: {type(obj)!r}")

def find_tools_repo_root() -> Path:
    """
    Walk upwards from this file until we find the Tools repo root.
    The Tools repo root is identified by containing an 'output' directory.
    """
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "output").is_dir():
            return parent
    raise RuntimeError(
        "Could not locate Tools repo root (folder containing 'output')."
    )


def env_default_out_root() -> Path:
    """
    Canonical output root for CAS public ingestion.
    Always resolves to:
      <Tools repo root>/output/cas_public_ingest
    """
    env = os.getenv("CAS_PUBLIC_INGEST_OUTROOT")
    if env:
        return Path(env).resolve()

    tools_root = find_tools_repo_root()
    return tools_root / "output" / "cas_public_ingest"

