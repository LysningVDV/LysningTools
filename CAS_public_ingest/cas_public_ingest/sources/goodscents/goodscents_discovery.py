from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Set
from datetime import datetime, timezone
import logging
import re
import csv
import yaml

from bs4 import BeautifulSoup

from cas_public_ingest.io_utils import env_default_out_root
from cas_public_ingest.normalize import normalize_cas
from cas_public_ingest.http_cache import HTTPCache


GS_RW_URL = "https://www.thegoodscentscompany.com/data/rw{rw_id}.html"
CAS_REGEX = re.compile(r"\b\d{2,7}-\d{2}-\d\b")


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def load_ifra_cas(out_root: Path) -> Set[str]:
    latest_ifra = out_root / "latest" / "ifra_dedup_by_cas.csv"
    if not latest_ifra.exists():
        raise FileNotFoundError(
            f"IFRA snapshot not found: {latest_ifra}"
        )

    cas_set: Set[str] = set()
    with open(latest_ifra, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            cas = normalize_cas(row.get("cas"))
            if cas:
                cas_set.add(cas)

    return cas_set


def extract_cas_numbers(html: str) -> List[str]:
    found = set(CAS_REGEX.findall(html))
    valid: List[str] = []

    for cas in found:
        cas_norm = normalize_cas(cas)
        if cas_norm:
            valid.append(cas_norm)

    return sorted(set(valid))


def classify_page(soup: BeautifulSoup) -> str:
    title = soup.find("title")
    if not title:
        return "GROUP"

    text = title.get_text(strip=True).lower()
    if any(w in text for w in ["mixture", "family", "group", "class"]):
        return "GROUP"

    return "MATERIAL"


def extract_primary_name(soup: BeautifulSoup) -> str | None:
    title = soup.find("title")
    if not title:
        return None
    return title.get_text(strip=True).split("-", 1)[0].strip()


def extract_synonyms(soup: BeautifulSoup) -> List[str]:
    synonyms = set()
    for b in soup.find_all("b"):
        if "Synonyms" in b.get_text():
            text = b.parent.get_text(" ", strip=True)
            parts = text.split(":", 1)
            if len(parts) == 2:
                for s in parts[1].split(","):
                    s = s.strip()
                    if s:
                        synonyms.add(s)
    return sorted(synonyms)


# ------------------------------------------------------------------
# Discovery Runner
# ------------------------------------------------------------------

def run_gs_discovery(
    run_tag: str,
    rw_start: int,
    rw_end: int,
    *,
    log_level: str = "INFO",
) -> None:

    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logger = logging.getLogger("GS_DISCOVERY")

    out_root = env_default_out_root()
    run_dir = out_root / "discovery" / run_tag
    run_dir.mkdir(parents=True, exist_ok=True)

    cache_dir = Path.home() / ".lysning_cache" / "goodscents"
    cache_dir.mkdir(parents=True, exist_ok=True)

    cache = HTTPCache(cache_dir=cache_dir, sleep_s=1.5)
    ifra_cas = load_ifra_cas(out_root)

    discovered: List[Dict] = []
    pages_no_cas: List[Dict] = []
    pages_group: List[Dict] = []

    stats = {
        "rw_start": rw_start,
        "rw_end": rw_end,
        "pages_attempted": 0,
        "pages_404": 0,
        "pages_group": 0,
        "pages_no_cas": 0,
        "ifra_overlap": 0,
        "discovered_cas": 0,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }

    for rw_id in range(rw_start, rw_end + 1):
        stats["pages_attempted"] += 1

        url = GS_RW_URL.format(rw_id=rw_id)
        resp = cache.get(url)

        if resp.status_code == 404:
            stats["pages_404"] += 1
            continue

        html = resp.path_text.read_text(encoding="utf-8", errors="replace")
        soup = BeautifulSoup(html, "html.parser")

        if classify_page(soup) == "GROUP":
            pages_group.append({"rw_id": rw_id, "url": url})
            stats["pages_group"] += 1
            continue

        cas_list = extract_cas_numbers(html)
        if not cas_list:
            pages_no_cas.append({"rw_id": rw_id, "url": url})
            stats["pages_no_cas"] += 1
            continue

        primary_name = extract_primary_name(soup)
        synonyms = extract_synonyms(soup)
        classification = "A" if len(cas_list) == 1 else "B"

        for cas in cas_list:
            if cas in ifra_cas:
                stats["ifra_overlap"] += 1
                continue

            discovered.append({
                "cas": cas,
                "primary_name": primary_name,
                "synonyms": "|".join(synonyms),
                "rw_id": rw_id,
                "source_url": url,
                "classification": classification,
                "multi_cas_source": classification == "B",
                "tier": "GOODSCENTS_ONLY",
                "discovered_at": datetime.now(timezone.utc).isoformat(),
            })
            stats["discovered_cas"] += 1

        if rw_id % 200 == 0:
            logger.info("Processed rw%s (%d discoveries)", rw_id, stats["discovered_cas"])

    # Write outputs
    def write_csv(path: Path, rows: List[Dict]) -> None:
        if not rows:
            return
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

    write_csv(run_dir / "goodscents_only_candidates.csv", discovered)
    write_csv(run_dir / "goodscents_pages_no_cas.csv", pages_no_cas)
    write_csv(run_dir / "goodscents_pages_skipped_groups.csv", pages_group)

    stats["finished_at"] = datetime.now(timezone.utc).isoformat()
    with open(run_dir / "ingest_metadata.yaml", "w", encoding="utf-8") as fh:
        yaml.safe_dump(stats, fh)

    logger.info("GS discovery completed: %d candidates", stats["discovered_cas"])

def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(
        description="Good Scents discovery (rw-ID enumeration)"
    )
    ap.add_argument("--run-tag", required=True)
    ap.add_argument("--rw-start", type=int, required=True)
    ap.add_argument("--rw-end", type=int, required=True)
    ap.add_argument("--log", default="INFO")

    args = ap.parse_args()

    run_gs_discovery(
        run_tag=args.run_tag,
        rw_start=args.rw_start,
        rw_end=args.rw_end,
        log_level=args.log,
    )


if __name__ == "__main__":
    raise SystemExit(main())