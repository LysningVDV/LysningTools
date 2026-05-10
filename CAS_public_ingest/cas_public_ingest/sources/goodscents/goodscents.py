from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Set
import argparse
import pandas as pd
import logging
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from types import SimpleNamespace

from cas_public_ingest.io_utils import env_default_out_root
from cas_public_ingest.normalize import normalize_cas
from cas_public_ingest.http_cache import HTTPCache


GOODSCENTS_CAS_SEARCH_URL = (
    "http://www.thegoodscentscompany.com/search3.php?qType=CAS&qString={cas}"
)


class GoodScentsIngestor:
    """
    Reference-grade public ingestor for the Good Scents Company database.

    CAS-first enrichment of the IFRA palette.
    """

    def __init__(self, config: Dict):
        self.config = config or {}

        self.out_root = env_default_out_root()
        self.cache_dir = self.out_root / "cache" / "goodscents"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.logger = logging.getLogger("GoodScentsIngestor")
        self.cache = HTTPCache(
            cache_dir=self.cache_dir,
            sleep_s=self.config.get("lookup", {}).get("throttle_seconds", 1.5),
        )

    # -------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------

    def ingest(self, context) -> Dict[str, pd.DataFrame]:
        self.logger.info("Starting Good Scents ingestion")

        run_tag = context.run_id
        run_dir = self.out_root / "runs" / run_tag
        run_dir.mkdir(parents=True, exist_ok=True)

        ifra_cas = self._load_ifra_cas(context)

        records = self._lookup_ifra_cas_first(ifra_cas)

        ifra_rows: List[Dict] = []
        gs_only_rows: List[Dict] = []

        for rec in records:
            cas = normalize_cas(rec["cas"])
            if not cas:
                continue

            if cas in ifra_cas:
                rec["tier"] = "IFRA"
                ifra_rows.append(rec)
            else:
                rec["tier"] = "GOODSCENTS_ONLY"
                gs_only_rows.append(rec)

        df_ifra = pd.DataFrame(ifra_rows)
        df_gs = pd.DataFrame(gs_only_rows)

        ifra_path = run_dir / "ifra_goodscents_enriched.csv"
        gs_path = run_dir / "goodscents_only_candidates.csv"

        df_ifra.to_csv(ifra_path, index=False)
        df_gs.to_csv(gs_path, index=False)

        self._update_latest(ifra_path, gs_path)

        self.logger.info(
            "Good Scents ingestion complete (%d IFRA enrichments)",
            len(df_ifra),
        )

        return {
            "ifra_enriched": df_ifra,
            "goodscents_only": df_gs,
        }

# -------------------------------------------------------------
# Internals
# -------------------------------------------------------------

    def _load_ifra_cas(self, context) -> Set[str]:
        """
        Load IFRA CAS set from pipeline context or from latest IFRA output.

        Raises:
            FileNotFoundError if IFRA has not been run yet.
        """
        if "ifra" in context.raw_sources:
            return set(context.raw_sources["ifra"]["cas"])

        latest_ifra = self.out_root / "latest" / "ifra_dedup_by_cas.csv"
        if not latest_ifra.exists():
            raise FileNotFoundError(
                "IFRA latest snapshot not found at "
                f"{latest_ifra}. Run IFRA ingestion first."
            )

        df = pd.read_csv(latest_ifra)
        return set(df["cas"].astype(str))


    def _lookup_ifra_cas_first(self, ifra_cas: Set[str]) -> List[Dict]:
        """
        Perform CAS-first Good Scents lookup for all IFRA CAS entries.
        """
        results: List[Dict] = []

        for cas in sorted(ifra_cas):
            rec = self._lookup_goodscents_cas(cas)
            if rec is not None:
                results.append(rec)

        self.logger.info(
            "Good Scents CAS-first lookup complete (%d hits)",
            len(results),
        )
        return results


    def _lookup_goodscents_cas(self, cas: str) -> Dict | None:
        """
        Perform a single CAS-first lookup against Good Scents.
        """
        url = GOODSCENTS_CAS_SEARCH_URL.format(cas=cas)
        resp = self.cache.get(url)

        html = resp.path_text.read_text(
            encoding="utf-8",
            errors="replace",
        )

        if "No results found" in html:
            return None

        soup = BeautifulSoup(html, "html.parser")

        record: Dict = {
            "cas": cas,
            "primary_name": None,
            "synonyms": [],
            "source": "GoodScents",
            "source_url": str(resp.url),
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
        }

        # Primary name from page title
        title = soup.find("title")
        if title:
            record["primary_name"] = (
                title.get_text(strip=True)
                .split("-", 1)[0]
                .strip()
            )

        # Synonyms (best-effort)
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

        record["synonyms"] = sorted(synonyms)

        if not record["primary_name"] and not record["synonyms"]:
            return None

        return record


    def _update_latest(self, *paths: Path) -> None:
        latest_dir = self.out_root / "latest"
        latest_dir.mkdir(exist_ok=True)

        for p in paths:
            if p.exists():
                (latest_dir / p.name).write_bytes(p.read_bytes())


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Good Scents CAS-first enrichment for IFRA materials"
    )
    ap.add_argument("--run-tag", required=True)
    ap.add_argument("--log", default="INFO")
    args = ap.parse_args()

    logging.basicConfig(level=getattr(logging, args.log.upper(), logging.INFO))

    out_root = env_default_out_root()
    run_dir = out_root / "runs" / args.run_tag
    run_dir.mkdir(parents=True, exist_ok=True)

    context = SimpleNamespace(
        run_id=args.run_tag,
        raw_sources={},
    )

    ingestor = GoodScentsIngestor(config={})
    ingestor.ingest(context)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())