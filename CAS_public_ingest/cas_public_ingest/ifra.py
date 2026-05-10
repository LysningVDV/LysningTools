from __future__ import annotations

import argparse
import json
import logging
import re
from dataclasses import asdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd
from bs4 import BeautifulSoup, Tag

from .http_cache import HTTPCache
from .io_utils import ensure_dir, env_default_out_root, utc_now_iso, write_jsonl
from .normalize import ParsedIFRARow, cas_checksum_ok, clean_name, normalize_cas

# ---------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------

IFRA_PAGE_URL = "https://ifrafragrance.org/transparency-list"
SPRIG_RENDER_ENDPOINT = "https://ifrafragrance.org/index.php/actions/sprig-core/components/render"
PAGE_OF_RE = re.compile(r"Page\s+\d+\s+of\s+(\d+)", re.IGNORECASE)

# ---------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------


def _setup_logger(log_path: Path, level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("cas_public_ingest.ifra")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    logger.propagate = False
    return logger


# ---------------------------------------------------------------------
# HTML parsing helpers
# ---------------------------------------------------------------------


def _find_table(soup: BeautifulSoup) -> Optional[Tag]:
    """
    Find the main IFRA results table by checking headers.
    """
    for table in soup.find_all("table"):
        headers = " ".join(
            th.get_text(" ", strip=True) for th in table.find_all("th")
        )
        if "CAS" in headers and "Principal name" in headers:
            return table
    return None


def _parse_rows(table: Tag, source_url: str, retrieved_at: str) -> List[Dict]:
    rows: List[Dict] = []

    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if not tds:
            continue

        cells = [td.get_text(" ", strip=True) for td in tds]

        rows.append(
            {
                "cas_raw": cells[0] if len(cells) >= 1 else "",
                "principal_name_raw": cells[1] if len(cells) >= 2 else "",
                "ncs_category_raw": cells[2] if len(cells) >= 3 else "",
                "source_url": source_url,
                "retrieved_at": retrieved_at,
            }
        )

    return rows


def _normalize_raw_rows(raw_rows: Iterable[Dict]) -> List[ParsedIFRARow]:
    parsed: List[ParsedIFRARow] = []

    for r in raw_rows:
        cas_raw = r.get("cas_raw", "")
        cas_norm = normalize_cas(cas_raw)
        checksum_ok = cas_checksum_ok(cas_norm) if cas_norm else None

        parsed.append(
            ParsedIFRARow(
                cas_raw=str(cas_raw),
                cas=cas_norm,
                cas_checksum_ok=checksum_ok,
                principal_name=clean_name(r.get("principal_name_raw", "")),
                ncs_category=clean_name(r.get("ncs_category_raw", "")),
                source_url=str(r.get("source_url", "")),
                retrieved_at=str(r.get("retrieved_at", "")),
            )
        )

    return parsed


def _dedupe_by_cas(df: pd.DataFrame) -> pd.DataFrame:
    df = df[df["cas"].notna() & (df["cas"] != "")]
    if df.empty:
        return df

    out = (
        df.groupby("cas", dropna=False)
        .agg(
            principal_names=("principal_name", lambda x: sorted(set(x))),
            ncs_categories=("ncs_category", lambda x: sorted(set(x))),
            source_urls=("source_url", lambda x: sorted(set(x))),
            last_retrieved_at=("retrieved_at", "max"),
            cas_checksum_ok=("cas_checksum_ok", "max"),
        )
        .reset_index()
    )

    return out


def _extract_last_page(html: str) -> int:
    """
    Extract total page count from 'Page X of Y'.
    """
    match = PAGE_OF_RE.search(html)
    if not match:
        raise RuntimeError("Could not determine last page number from IFRA HTML.")
    return int(match.group(1))


def _extract_sprig_config(html: str) -> str:
    """
    Extract the sprig:config JSON blob from the component.
    """
    soup = BeautifulSoup(html, "html.parser")
    comp = soup.find(class_=re.compile(r"\bsprig-component\b"))
    if not comp:
        raise RuntimeError("sprig-component not found in IFRA HTML")

    hx_vals = comp.get("data-hx-vals")
    if not hx_vals:
        raise RuntimeError("data-hx-vals missing on sprig-component")

    vals = json.loads(hx_vals)
    if "sprig:config" not in vals:
        raise RuntimeError("sprig:config missing in data-hx-vals")

    return vals["sprig:config"]


# ---------------------------------------------------------------------
# Main scraper
# ---------------------------------------------------------------------


def scrape_ifra(
    out_run_dir: Path,
    cache_dir: Path,
    force: bool = False,
    sleep_s: float = 1.0,
    log_level: str = "INFO",
) -> Tuple[pd.DataFrame, pd.DataFrame]:

    ensure_dir(out_run_dir)
    ensure_dir(cache_dir)

    logger = _setup_logger(out_run_dir / "run.log", level=log_level)
    logger.info("Starting IFRA scrape (Sprig-aware)")

    cache = HTTPCache(cache_dir=cache_dir, sleep_s=sleep_s)

    # --- Page 1 ---
    fr1 = cache.get(IFRA_PAGE_URL, force=force)
    html1 = fr1.path_text.read_text(encoding="utf-8", errors="replace")

    sprig_config = _extract_sprig_config(html1)
    last_page = _extract_last_page(html1)
    logger.info(f"Detected {last_page} pages")

    raw_rows: List[Dict] = []

    soup1 = BeautifulSoup(html1, "html.parser")
    table1 = _find_table(soup1)
    if not table1:
        raise RuntimeError("Results table not found on page 1")

    rows1 = _parse_rows(table1, IFRA_PAGE_URL, fr1.retrieved_at)
    raw_rows.extend(rows1)
    logger.info(f"Page 1: {len(rows1)} rows")

    # --- Pages 2..N via Sprig ---
    headers = {
        "HX-Request": "true",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Referer": IFRA_PAGE_URL,
    }

    for page in range(2, last_page + 1):
        payload = {
            "sprig:config": sprig_config,
            "page": str(page),
            "query": "",
        }

        fr = cache.post(
            SPRIG_RENDER_ENDPOINT,
            data=payload,
            headers=headers,
            force=force,
        )

        html = fr.path_text.read_text(encoding="utf-8", errors="replace")
        soup = BeautifulSoup(html, "html.parser")
        table = _find_table(soup)

        if not table:
            logger.warning(f"Page {page}: no table found")
            continue

        rows = _parse_rows(table, f"page={page}", fr.retrieved_at)
        raw_rows.extend(rows)
        logger.info(f"Page {page}: {len(rows)} rows")

    logger.info(f"Total raw rows collected: {len(raw_rows)}")

    # --- Write outputs ---
    write_jsonl(out_run_dir / "ifra_raw.jsonl", raw_rows)

    parsed = _normalize_raw_rows(raw_rows)
    parsed_df = pd.DataFrame(asdict(p) for p in parsed)
    parsed_df.to_csv(out_run_dir / "ifra_parsed.csv", index=False)

    dedup_df = _dedupe_by_cas(parsed_df)
    dedup_df.to_csv(out_run_dir / "ifra_dedup_by_cas.csv", index=False)

    meta = {
        "run_started_at": utc_now_iso(),
        "pages": last_page,
        "raw_rows": len(raw_rows),
        "unique_cas": len(dedup_df),
    }

    import yaml

    (out_run_dir / "ingest_metadata.yaml").write_text(
        yaml.safe_dump(meta, sort_keys=False), encoding="utf-8"
    )

    logger.info("IFRA scrape finished successfully")
    return parsed_df, dedup_df


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser("Scrape IFRA Transparency List")
    ap.add_argument("--run-tag", required=True)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--sleep", type=float, default=1.0)
    ap.add_argument("--log", default="INFO")

    args = ap.parse_args(argv)


    out_root = env_default_out_root()
    run_dir = out_root / "runs" / args.run_tag
    cache_dir = out_root / "cache" / "ifra"
    latest_dir = out_root / "latest"


    scrape_ifra(
        out_run_dir=run_dir,
        cache_dir=cache_dir,
        force=args.force,
        sleep_s=args.sleep,
        log_level=args.log,
    )

    latest = ensure_dir(out_root / "latest")
    for name in [
        "ifra_raw.jsonl",
        "ifra_parsed.csv",
        "ifra_dedup_by_cas.csv",
        "ingest_metadata.yaml",
        "run.log",
    ]:
        p = run_dir / name
        if p.exists():
            (latest / name).write_bytes(p.read_bytes())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())