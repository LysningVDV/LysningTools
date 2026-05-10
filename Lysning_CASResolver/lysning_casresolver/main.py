import argparse
from email import parser
import logging
import os
from datetime import datetime, UTC, time
from logging.handlers import MemoryHandler
from pathlib import Path
import json
from time import perf_counter
import pandas as pd
from tqdm import tqdm

from .io.excel_io import read_input_excel, write_output_excel
from .resolution.cas_lookup import resolve_cas
from .resolution.name.resolver import resolve_name
from .resolution.opsin_lookup import resolve_opsin_cas
from .util.helpers import classify_mixture_enhanced, inchi_to_smiles
from .util.validate import validate_cas

from canonical_common.cas_registry import (
    load_or_init_allowlist,
    read_registry_excel,
    upsert_registry,
    write_registry_excel_atomic,
    export_registry_csv,
    export_registry_sqlite,
    write_audit_workbook_atomic,
    backup_registry_to_onedrive,
    get_db2_local_paths,
    REGISTRY_SHEET,
)
from canonical_common.cas_registry_adapters import incoming_from_resolver


logger = logging.getLogger(__name__)

def prevent_sleep_windows() -> None:
    """
    Prevent Windows from sleeping while process runs. Safe no-op if fails.
    """
    try:
        import ctypes
        ES_CONTINUOUS = 0x80000000
        ES_SYSTEM_REQUIRED = 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
    except Exception:
        pass

# ---------------------------------------------------------------------
#HOOK USAGE for DB2 registry update :
# ---------------------------------------------------------------------

def _repo_root_from_this_file() -> Path:
    """
    This file is: .../Tools/Lysning_CASResolver/lysning_casresolver/main.py
    parents[2] -> .../Tools
    """
    return Path(__file__).resolve().parents[2]


def _load_db2_context(repo_root: Path | None = None):
    """
    Load DB2 governance + local paths + allowlist + existing registry.

    Returns:
      repo_root, governance_root, schema_path, audit_path, backups_dir,
      allowlist, paths, existing_registry_df
    """
    if repo_root is None:
        repo_root = _repo_root_from_this_file()

    governance_root = repo_root / "Canonical_DB"

    schema_path = governance_root / "cas_registry_schema.json"
    audit_path  = governance_root / "cas_registry_audit.xlsx"
    backups_dir = governance_root / "backups_registry"

    allowlist = load_or_init_allowlist(schema_path)
    paths = get_db2_local_paths()

    # IMPORTANT: make sure we read the correct sheet
    existing = read_registry_excel(paths["xlsx"], allowlist, sheet_name=REGISTRY_SHEET)

    return (
        repo_root, governance_root, schema_path, audit_path, backups_dir,
        allowlist, paths, existing
    )
def _update_db2_registry_from_resolver_df(df_output: pd.DataFrame) -> None:
    if df_output is None or len(df_output) == 0:
        return

    (
        repo_root, governance_root, schema_path, audit_path, backups_dir,
        allowlist, paths, existing
    ) = _load_db2_context()

    # Adapt resolver-native columns -> DB2 schema columns
    incoming = incoming_from_resolver(df_output)

    # Always-on guard: if everything becomes mixture, adapter logic is likely wrong.
    if incoming["cas_status"].astype(str).str.lower().eq("mixture").all():
        logger.warning(
            "DB2 adapter produced cas_status='mixture' for all %d rows. "
            "This is likely a mixture_type mapping bug. Proceeding anyway.",
            len(incoming),
        )

    if incoming["cas_number_normalized"].astype(str).str.strip().eq("").all():
        logger.warning(
            "DB2 registry update skipped: incoming has empty cas_number_normalized for all rows (adapter mismatch)."
        )
        return

    result = upsert_registry(existing, incoming, allowlist)

    # Write local DB2 + exports
    write_registry_excel_atomic(paths["xlsx"], result.updated_registry)
    export_registry_csv(result.updated_registry, paths["csv"])
    export_registry_sqlite(result.updated_registry, paths["sqlite"])

    # Governance audit + backup
    write_audit_workbook_atomic(audit_path, result.audit, result.rejected)
    backup_registry_to_onedrive(paths["xlsx"], backups_dir)
    
    # Always-on guard: if everything becomes mixture, adapter logic is likely wrong.
    # Allow it only if you truly expect a 100% mixture batch (rare).
    if incoming["cas_status"].astype(str).str.lower().eq("mixture").all():
        logger.warning(
            "DB2 adapter produced cas_status='mixture' for all %d rows. "
            "This is likely a mixture_type mapping bug. Proceeding anyway.",
            len(incoming),
        )


    # Optional: guard against adapter mismatch causing all rows to be rejected
    if incoming["cas_number_normalized"].astype(str).str.strip().eq("").all():
        logger.warning("DB2 registry update skipped: incoming has empty cas_number_normalized for all rows (adapter mismatch).")
        return

    result = upsert_registry(existing, incoming, allowlist)

    # Write local DB2 + exports
    write_registry_excel_atomic(paths["xlsx"], result.updated_registry)
    export_registry_csv(result.updated_registry, paths["csv"])
    export_registry_sqlite(result.updated_registry, paths["sqlite"])

    # Governance audit + backup
    write_audit_workbook_atomic(audit_path, result.audit, result.rejected)
    backup_registry_to_onedrive(paths["xlsx"], backups_dir)



# ---------------------------------------------------------------------
# OUTPUT UTILITIES
# ---------------------------------------------------------------------

DEFAULT_OUTPUT_DIR = "output"

def ensure_output_folder(path: str) -> str:
    
    if path is None:
        return None
    folder = os.path.dirname(path)
    if folder and not os.path.exists(folder):
        os.makedirs(folder, exist_ok=True)
    return path


def timestamped_path(path: str) -> str:
    base, ext = os.path.splitext(path)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    return f"{base}_{stamp}{ext}"


def auto_increment_path(path: str) -> str:
    base, ext = os.path.splitext(path)
    i = 1
    new_path = f"{base} ({i}){ext}"
    while os.path.exists(new_path):
        i += 1
        new_path = f"{base} ({i}){ext}"
    return new_path


# ---------------------------------------------------------------------
# ROW BUILDERS
# ---------------------------------------------------------------------

def _row_from_cas_result(raw_value, result, original_name, cas_validity):
    smiles = result.get("smiles") or inchi_to_smiles(result.get("inchi"))
    mixture = classify_mixture_enhanced(original_name, raw_value, smiles)

    return {
        "input": raw_value,
        "cas": result.get("cas", ""),
        "smiles": smiles,
        "inchi": result.get("inchi", ""),
        "inchikey": result.get("inchikey", ""),
        "mw": result.get("mw", ""),
        "source": result.get("source", ""),
        "warning": result.get("warning", ""),
        "mixture_type": mixture,
        "cas_validity": cas_validity,
        "timestamp": result.get("timestamp") or datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }


def _row_from_name_result(raw_value, best, warnings, original_cas):
    smiles = best.get("smiles") or inchi_to_smiles(best.get("inchi"))
    mixture = classify_mixture_enhanced(raw_value, original_cas, smiles)

    return {
        "input": raw_value,
        "cas": "",
        "smiles": smiles,
        "inchi": best.get("inchi", ""),
        "inchikey": best.get("inchikey", ""),
        "mw": best.get("mw", ""),
        "source": best.get("source", "name_lookup"),
        "warning": "; ".join(warnings),
        "mixture_type": mixture,
        "cas_validity": "",
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }


def _row_from_opsin_result(raw_value, original_cas, opsin):
    smiles = opsin.get("smiles") or inchi_to_smiles(opsin.get("inchi"))
    mixture = classify_mixture_enhanced(raw_value, original_cas, smiles)

    return {
        "input": raw_value,
        "cas": "",
        "smiles": smiles,
        "inchi": opsin.get("inchi", ""),
        "inchikey": opsin.get("inchikey", ""),
        "mw": opsin.get("mw", None),
        "source": "opsin",
        "warning": "; ".join(opsin.get("warning_list", [])),
        "mixture_type": mixture,
        "cas_validity": "",
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }


def _empty_failure_row(raw_value, reason):
    return {
        "input": raw_value,
        "cas": "",
        "smiles": "",
        "inchi": "",
        "inchikey": "",
        "mw": "",
        "source": "unresolved",
        "warning": reason,
        "mixture_type": "unknown",
        "cas_validity": "",
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }

def build_db2_cache_lookup(db2_registry_df):
    # normalize key
    reg = db2_registry_df.copy()
    reg["cas_number_normalized"] = reg["cas_number_normalized"].astype(str).str.strip()
    reg["cas_status"] = reg["cas_status"].astype(str).str.lower().str.strip()
    reg["inchi_key"] = reg["inchi_key"].astype(str).str.strip()

    eligible = reg[
        (reg["cas_number_normalized"] != "")
        & (reg["inchi_key"] != "")
        & (reg["cas_status"] == "valid")
    ].copy()

    # Keep last occurrence if duplicates exist
    eligible = eligible.drop_duplicates(subset=["cas_number_normalized"], keep="last")

    # Dict: cas -> row dict
    return {row["cas_number_normalized"]: row for _, row in eligible.iterrows()}

# ---------------------------------------------------------------------
# MULTI‑CAS HELPER
# ---------------------------------------------------------------------

def split_cas_candidates(raw_cas: str) -> list[str]:
    if not raw_cas:
        return []
    normalized = raw_cas.replace("\\", "/").replace("\u00A0", " ")
    return [c.strip() for c in normalized.split("/") if c.strip()]


# ---------------------------------------------------------------------
# CORE RESOLUTION
# ---------------------------------------------------------------------


def resolve_dataframe(
    df: pd.DataFrame,
    db2_cache: dict[str, dict] | None = None,
    cache_only: bool = False,
) -> tuple[pd.DataFrame, dict]:
    # --- Column hygiene (keep!) ---
    df.columns = (
        df.columns.str.replace("'", "", regex=False)
                  .str.replace("\u00A0", " ", regex=False)
                  .str.replace("\ufeff", "", regex=False)
                  .str.strip()
    )


    if "Name" not in df.columns or "CAS" not in df.columns:
        raise ValueError("Input Excel must contain Name and CAS")

    output_rows = []

    # Counters
    count_cas = 0
    count_pubchem = 0
    count_opsin = 0
    count_cactus = 0
    count_name_lookup = 0
    count_chemspider = 0
    count_unresolved = 0
    count_db2_cache = 0
    count_db2_cache_miss = 0

    total_rows = len(df)
    logger.info("Starting resolution of %d rows", total_rows)

    iterator = df.iterrows()
    if not logger.isEnabledFor(logging.DEBUG):
        iterator = tqdm(iterator, total=total_rows, desc="Resolving", ncols=80)

    cs_handler = MemoryHandler(capacity=20000, target=None)
    logger.addHandler(cs_handler)

    start = datetime.now()

    for idx, row in iterator:

        raw_name = str(row["Name"]).strip()
        raw_cas_input = str(row["CAS"]).strip()

        try:
            # -------------------------------------------------
            # MULTI‑CAS PATH
            # -------------------------------------------------
            if raw_cas_input != "":
                candidates = split_cas_candidates(raw_cas_input)

                # 1. Validate CAS numbers
                valid_candidates = []
                for c in candidates:
                    try:
                        validate_cas(c)
                        valid_candidates.append(c)
                    except Exception:
                        continue

                cas_results = []

                # 2. Resolve each candidate — DB2 cache first (conservative)
                for c in valid_candidates:
                    cs_handler.buffer.clear()

                    # --- DB2-first cache short-circuit ---
                    cached = None
                    if db2_cache is not None:
                        key = str(c).strip()
                        cached = db2_cache.get(key)


                    if cached is not None:
                        count_db2_cache += 1
                        tmp = dict(cached)
                        tmp["cas"] = c
                        tmp["chemspider_used"] = False
                        tmp["source"] = "db2_cache"
                        cas_results.append(tmp)
                        continue
                    else:
                        count_db2_cache_miss += 1
                    
                    if cache_only:
                        # Cache-only mode: do not attempt network resolution for misses
                        continue

                    # --- Normal resolution ---
                    try:
                        res = resolve_cas(c)                        
                        if not res:
                            continue
                        chemspider_used = any(
                            "CHEMSPIDER_USED" in rec.getMessage()
                            for rec in cs_handler.buffer
                        )

                        tmp = dict(res)
                        tmp["cas"] = c
                        tmp["chemspider_used"] = chemspider_used
                        cas_results.append(tmp)
                    except Exception:
                        continue

                # 3. Select winner via ranking
                def rank_for(result):
                    src = (result.get("source") or "").lower()
                    cs = result.get("chemspider_used")
                    if src == "db2_cache":
                        return 0
                    if src == "cas":
                        if cs:
                            return 2   # CAS + ChemSpider
                        return 1       # Pure CAS
                    if src == "pubchem":
                        return 3
                    if src == "cactus":
                        return 4
                    if src == "opsin":
                        return 5
                    if src == "rdkit":
                        return 6
                    return 7

                if cas_results:
                    sorted_results = sorted(cas_results, key=rank_for)
                    winner = sorted_results[0]
                    others = sorted_results[1:]
                else:
                    winner = None
                    others = []

                if winner:
                    final = _row_from_cas_result(
                        winner["cas"], winner, raw_name, "valid"
                    )

                    final["cas_used"] = winner["cas"]
                    final["original_name"] = raw_name
                    final["original_cas"] = raw_cas_input

                    alt_list = []
                    for o in others:
                        alt_list.append({
                            "cas": o["cas"],
                            "smiles": o.get("smiles", ""),
                            "source": o.get("source", "")
                        })
                    final["alternate_cas_hits"] = str(alt_list)

                    if winner.get("chemspider_used") or any(
                        o.get("chemspider_used") for o in others
                    ):
                        count_chemspider += 1

                    src = (winner.get("source") or "").lower()
                    if src == "db2_cache":
                        # treat cache hit as success, but separate from "new" resolution
                        pass
                    elif src == "cas":
                        count_cas += 1
                    elif src == "pubchem":
                        count_pubchem += 1
                    elif src == "opsin":
                        count_opsin += 1
                    elif src == "cactus":
                        count_cactus += 1
                    else:
                        count_unresolved += 1

                else:
                    final = _empty_failure_row(raw_name, "unresolved CAS (no valid results)")
                    final["original_name"] = raw_name
                    final["original_cas"] = raw_cas_input
                    final["cas_used"] = ""
                    final["alternate_cas_hits"] = str([])
                    count_unresolved += 1

            # -------------------------------------------------
            # NAME PATH
            # -------------------------------------------------
            else:
                name_result = resolve_name(raw_name)

                if name_result:
                    best = name_result["best"]
                    warnings = name_result["warning_list"]
                    final = _row_from_name_result(raw_name, best, warnings, raw_cas_input)
                    final["cas_used"] = ""
                    final["alternate_cas_hits"] = str([])
                    count_name_lookup += 1

                else:
                    opsin = resolve_opsin_cas(raw_name)
                    if opsin:
                        final = _row_from_opsin_result(raw_name, raw_cas_input, opsin)
                        final["cas_used"] = ""
                        final["alternate_cas_hits"] = str([])
                        count_opsin += 1
                    else:
                        final = _empty_failure_row(raw_name, "unresolved name (PubChem + OPSIN)")
                        final["cas_used"] = ""
                        final["alternate_cas_hits"] = str([])
                        count_unresolved += 1

                final["original_name"] = raw_name
                final["original_cas"] = raw_cas_input

        except Exception as exc:
            logger.error("Error resolving row %d: %s", idx, exc)
            final = _empty_failure_row(raw_name, f"exception: {exc}")
            final["original_name"] = raw_name
            final["original_cas"] = raw_cas_input
            final["cas_used"] = ""
            final["alternate_cas_hits"] = str([])
            count_unresolved += 1

        output_rows.append(final)

    logger.removeHandler(cs_handler)

    elapsed = datetime.now() - start

    summary = {
        "resolved_cas": count_cas,
        "resolved_pubchem": count_pubchem,
        "resolved_opsin": count_opsin,
        "resolved_cactus": count_cactus,
        "resolved_name_lookup": count_name_lookup,
        "chemspider_used": count_chemspider,
        "cached_db2_hits": count_db2_cache,
        "cached_db2_misses": count_db2_cache_miss,
        "cache_only": bool(cache_only),
        "unresolved": count_unresolved,
        "total": total_rows,
        "runtime": str(elapsed)
    }

    return pd.DataFrame(output_rows), summary


def _find_tools_root(start: Path) -> Path:
    """
    Walk upward until we find the Tools repo root (identified by Canonical_DB folder).
    """
    p = start.resolve()
    for parent in [p, *p.parents]:
        if (parent / "Canonical_DB").exists():
            return parent
    return p

def _utc_stamp() -> str:
    # Collision-proof UTC stamp
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")

# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------

def main():

    parser = argparse.ArgumentParser(description="Lysning CAS → SMILES Resolver")
    parser.add_argument("input", help="Path to input Excel file")
    parser.add_argument(
        "output",
        nargs="?",
        default=None,
        help="Optional output path. If omitted, output is written under Tools/output/CASResolver/.",
    )

    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
    "--cache-only",
    action="store_true",
    help="Use DB2 cache only: do not resolve cache misses via PubChem/Cactus/etc. (fast rerun/offline mode).",
)

    args = parser.parse_args()

    tools_root = _find_tools_root(Path(__file__).resolve())
    default_outdir = tools_root / "output" / "CASResolver"
    default_outdir.mkdir(parents=True, exist_ok=True)

    run_stamp = _utc_stamp()  # <-- MUST be before args.output assignment

    if args.output is None:
        args.output = str(default_outdir / f"casresolver_output_{run_stamp}.xlsx")

    if args.output:
        output_path = Path(args.output).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        output_path = default_outdir / f"casresolver_output_{run_stamp}.xlsx"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    prevent_sleep_windows()
    logger.info("Sleep prevention activated.")
    
    t0_wall = datetime.now(UTC)
    t0_perf = perf_counter()
    
    # Option B: output is optional. Only normalize/create folder if a path is provided.
    if args.output is not None:
        args.output = ensure_output_folder(args.output)

    if os.path.exists(args.output) and not args.force:
        new = timestamped_path(args.output)
        if os.path.exists(new):
            new = auto_increment_path(new)
        logger.warning("Output exists, writing instead to %s", new)
        args.output = new

    df_input = read_input_excel(args.input)
    
    # --- Load DB2 registry for cache short-circuit (sheet: registry) ---
    (
        repo_root, governance_root, schema_path, audit_path, backups_dir,
        allowlist, paths, db2_registry_df
    ) = _load_db2_context(repo_root=tools_root)

    db2_cache = build_db2_cache_lookup(db2_registry_df)
    logger.info("DB2 cache enabled (eligible entries=%d)", len(db2_cache))
    df_output, summary = resolve_dataframe(df_input, db2_cache=db2_cache, cache_only=args.cache_only)


    logger.info("DB2 registry update: starting (rows=%d)", len(df_output))
    _update_db2_registry_from_resolver_df(df_output)
    logger.info("DB2 registry update: done")

    write_output_excel(df_output, args.output)

    logger.info(
        "\n========== RESOLUTION SUMMARY =========="
        f"\nTotal rows:             {summary['total']}"
        f"\nResolved via CAS:       {summary['resolved_cas']}"
        f"\nResolved via PubChem:   {summary['resolved_pubchem']}"
        f"\nResolved via OPSIN:     {summary['resolved_opsin']}"
        f"\nResolved via Cactus:    {summary['resolved_cactus']}"
        f"\nResolved via NameLookup:{summary['resolved_name_lookup']}"
        f"\nChemSpider usages:      {summary['chemspider_used']}"
        f"\nCached via DB2:         {summary['cached_db2_hits']}"
        f"\nDB2 cache misses:       {summary['cached_db2_misses']}"
        f"\nCache-only mode:        {summary.get('cache_only', False)}"
        f"\nUnresolved:             {summary['unresolved']}"
        f"\nRuntime:                {summary['runtime']}"
        "\n=========================================\n"
    )

    total_wall = datetime.now(UTC) - t0_wall
    total_perf = perf_counter() - t0_perf

    logger.info(f"\nOutput written to:\n   {args.output}\n")
    logger.info("Total wall time: %s", str(total_wall))
    logger.info("Total active time (perf): %.2fs", total_perf)


if __name__ == "__main__":
    main()