from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
import yaml
import argparse


def run_command(cmd: list[str]) -> None:
    """Run a subprocess and wait for completion."""
    print(">>", " ".join(cmd))
    proc = subprocess.run(cmd)
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}")


def read_discovered_cas(meta_path: Path) -> int:
    """Read discovered_cas count from ingest_metadata.yaml."""
    if not meta_path.exists():
        raise FileNotFoundError(f"Missing metadata: {meta_path}")

    with meta_path.open("r", encoding="utf-8") as fh:
        meta = yaml.safe_load(fh)

    return int(meta.get("discovered_cas", 0))


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Adaptive Good Scents discovery controller"
    )
    ap.add_argument("--anchors", nargs="+", type=int, required=True,
                    help="Known-good rw anchors (e.g. 1375541 1432721)")
    ap.add_argument("--initial-radius", type=int, default=100,
                    help="Initial half-window around anchor")
    ap.add_argument("--step", type=int, default=250,
                    help="Expansion step size")
    ap.add_argument("--max-radius", type=int, default=1500,
                    help="Maximum expansion radius per anchor")
    ap.add_argument("--log", default="INFO",
                    help="Log level for discovery runs")

    args = ap.parse_args()

    tool_root = Path.cwd()
    out_root = tool_root / "output" / "cas_public_ingest" / "discovery"

    for anchor in args.anchors:
        print(f"\n=== Exploring GS anchor rw{anchor} ===")

        radius = args.initial_radius
        zero_hit_streak = 0

        while radius <= args.max_radius and zero_hit_streak < 2:
            rw_start = anchor - radius
            rw_end = anchor + radius
            tag = f"GS_DISCOVERY_rw{anchor}_r{radius}"

            print(f"\nRunning discovery window:")
            print(f"  rw_start = {rw_start}")
            print(f"  rw_end   = {rw_end}")
            print(f"  tag      = {tag}")

            cmd = [
                sys.executable,
                "-m", "cas_public_ingest.goodscents_discovery",
                "--run-tag", tag,
                "--rw-start", str(rw_start),
                "--rw-end", str(rw_end),
                "--log", args.log,
            ]

            run_command(cmd)

            meta_path = out_root / tag / "ingest_metadata.yaml"
            discovered = read_discovered_cas(meta_path)

            if discovered == 0:
                zero_hit_streak += 1
                print(f"→ No discoveries (streak {zero_hit_streak})")
            else:
                zero_hit_streak = 0
                print(f"→ {discovered} discoveries found, expanding")

            radius += args.step

        print(f"\n✔ Finished anchor rw{anchor}")

    print("\n✅ Adaptive GS discovery completed")


if __name__ == "__main__":
    raise SystemExit(main())