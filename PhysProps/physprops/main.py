"""
Main integration module for the Physical Properties Retrieval App.

Implements:
- Per-row multi-identifier fallback (Priority B)
- Strict identifier validation
- Column-name + pattern-based candidate detection
- Combined results: experimental/computed/final with sources
- CLI interface
- High-level resolve_dataframe()

Priority Order B for identifiers:
    SMILES > InChI > InChIKey > CAS > Name
"""
import argparse
import logging
import shutil
from pathlib import Path
from typing import Dict, Any, List

import pandas as pd
from rdkit import Chem
from physprops.util.identify import normalize_identifier, detect_identifier_type
from physprops.util.normalize import clean_whitespace, normalize_cas
from physprops.sources.pubchem import get_pubchem_properties
from physprops.compute.rdkit import compute_rdkit_descriptors
from physprops.sources.fallbacks import apply_fallbacks
from physprops.io.excel_io import (
    load_excel,
    save_excel,
    integrate_results_into_dataframe,
    export_physprops_wide,
)
from physprops.sources.enrich import enrich_hsp_columns, enrich_henry_columns
from canonical_common.canonical_db import (
    load_or_init_allowlist,
    read_xlsx,
    write_xlsx_atomic,
    sanitize_outgoing,
    upsert_canonical,
)

logger = logging.getLogger(__name__)

ONEDRIVE_CANONICAL_ROOT = Path(r"C:\Users\vdevi\OneDrive - Lysning Innovation Consultants B.V\Lysning\Tools\Canonical_DB")
ONEDRIVE_CANONICAL_ROOT.mkdir(parents=True, exist_ok=True)
CANONICAL_ROOT_DIR = ONEDRIVE_CANONICAL_ROOT  # backward-compat alias

# Global cache for identifier -> results (parallel-safe for reads)
CACHE = {}

# ------------------------------------------------------------
# Column name patterns (Option B: name + content detection)
# ------------------------------------------------------------

COLNAME_PATTERNS = {
    "smiles": ["smiles", "structure", "struct", "smile"],
    "inchi": ["inchi", "inchi string"],
    "inchikey": ["inchikey", "inchi key"],
    "cas": ["cas", "cas no", "cas number", "cas nr"],
    "name": ["name", "chemical", "substance", "compound"]
}

PRIORITY_ORDER = ["smiles", "inchi", "inchikey", "cas", "name"]




# ------------------------------------------------------------
# Helper: does value look like SMILES?
# ------------------------------------------------------------

def _looks_like_smiles_value(val: str) -> bool:
    if not isinstance(val, str):
        return False
    if " " in val:
        return False
    try:
        mol = Chem.MolFromSmiles(val)
        return mol is not None
    except Exception:
        return False


# ------------------------------------------------------------
# Helper: does value look like CAS?
# ------------------------------------------------------------

def _looks_like_cas(val: str) -> bool:
    if not isinstance(val, str):
        return False
    return normalize_cas(val) is not None


# ------------------------------------------------------------
# Identify candidate identifier columns
# ------------------------------------------------------------

def get_candidate_identifier_columns(df: pd.DataFrame) -> Dict[str, List[str]]:
    """
    Detect which DataFrame columns may contain identifiers using:
    - Column name matching (Option B)
    - Pattern recognition (Option B)
    """
    candidates = {k: [] for k in PRIORITY_ORDER}

    # --- Pass 1: column name matching ---
    for col in df.columns:
        col_lower = col.lower().strip()

        for idtype, patterns in COLNAME_PATTERNS.items():
            if any(p in col_lower for p in patterns):
                if col not in candidates[idtype]:
                    candidates[idtype].append(col)

    # --- Pass 2: content-based inference ---
    for col in df.columns:
        values = df[col].dropna().astype(str)

        # Try identify SMILES
        if col not in sum(candidates.values(), []):
            if any(_looks_like_smiles_value(v) for v in values.head(50)):
                candidates["smiles"].append(col)
                continue

        # Try identify InChI
        if col not in sum(candidates.values(), []):
            if any(v.startswith("InChI=") for v in values.head(50)):
                candidates["inchi"].append(col)
                continue

        # Try CAS
        if col not in sum(candidates.values(), []):
            if any(_looks_like_cas(v) for v in values.head(50)):
                candidates["cas"].append(col)
                continue

    # Ensure we always have at least one fallback name column
    if not candidates["name"]:
        candidates["name"].append(df.columns[0])

    return candidates


# ------------------------------------------------------------
# Pick best identifier for a single row
# ------------------------------------------------------------

def pick_best_identifier(row, candidates: Dict[str, List[str]]) -> Dict[str, Any]:
    """
    For a single row, choose the best identifier according to:
        Priority B + strict validation
    """
    warnings = []

    for idtype in PRIORITY_ORDER:
        for col in candidates.get(idtype, []):
            raw = row.get(col)
            if raw is None:
                continue

            raw_str = str(raw).strip()
            if raw_str == "":
                continue

            # --- Strict validation rules ---
            if idtype == "smiles":
                if _looks_like_smiles_value(raw_str):
                    return {"identifier_value": raw_str, "identifier_type": "smiles", "warnings": warnings}

            elif idtype == "inchi":
                if raw_str.startswith("InChI="):
                    try:
                        mol = Chem.MolFromInchi(raw_str)
                        if mol is not None:
                            return {"identifier_value": raw_str, "identifier_type": "inchi", "warnings": warnings}
                    except Exception:
                        continue

            elif idtype == "inchikey":
                if detect_identifier_type(raw_str) == "inchikey":
                    return {"identifier_value": raw_str.upper(), "identifier_type": "inchikey", "warnings": warnings}

            elif idtype == "cas":
                normalized = normalize_cas(raw_str)
                if normalized:
                    return {"identifier_value": normalized, "identifier_type": "cas", "warnings": warnings}

            elif idtype == "name":
                return {"identifier_value": raw_str, "identifier_type": "name", "warnings": warnings}

    warnings.append("No usable identifier found.")
    return {"identifier_value": None, "identifier_type": None, "warnings": warnings}


# ------------------------------------------------------------
# Build final fields
# ------------------------------------------------------------

def build_final_fields(flat: Dict[str, Any]) -> Dict[str, Any]:
    """
    final = experimental if exists else computed
    source updated accordingly
    """

    PROPS = [
        "boiling_point_c",
        "melting_point_c",
        "flash_point_c",
        "autoignition_temp_c",
        "vapor_pressure_pa",
        "water_solubility_mg_l",
        "refractive_index",
        "density_g_ml",
        "logp",
        "heat_of_vaporization_kj_mol",
        "critical_temp_c",
        "critical_pressure_bar",
        "mw",
        "exact_mass",
        "clogp",
        "tpsa",
        "hbd",
        "hba",
        "rot_bonds",
        "ring_count",
        "fraction_csp3",
        "molar_refractivity",
        "smiles",
        "inchi",
        "inchikey"
    ]

    for prop in PROPS:
        exp_val = flat.get(f"experimental_{prop}")
        comp_val = flat.get(f"computed_{prop}")
        src_key = f"source_{prop}"

        if exp_val is not None:
            flat[f"final_{prop}"] = exp_val
            flat[src_key] = "pubchem"

        elif comp_val is not None:
            flat[f"final_{prop}"] = comp_val
            if flat.get(src_key) is None:
                flat[src_key] = "computed"

        else:
            flat[f"final_{prop}"] = None
            flat[src_key] = None

    return flat


# ------------------------------------------------------------
# Resolve a single identifier value
# ------------------------------------------------------------

def resolve_identifier(value: str, id_type: str) -> Dict[str, Any]:
    """
    Normalize → RDKit → PubChem → fallback → merge.
    """

    if value is None or str(value).strip() == "":
        return {"warnings": ["Empty identifier"], "timestamp": pd.Timestamp.now("UTC").isoformat()}

    cleaned = clean_whitespace(value)
    normalized = normalize_identifier(cleaned, id_type)

    flat = {
        "input": value,
        "normalized_input": normalized,
        "identifier_type": id_type,
        "warnings": []
    }

    # --- RDKit ---
    rd = compute_rdkit_descriptors(normalized, id_type)
    for k, v in rd.items():
        flat[k] = v
    flat["warnings"].extend(rd.get("warnings", []))

    # --- PubChem ---
    pub = get_pubchem_properties(normalized, id_type)
    for k, v in pub.items():
        if k == "warnings":
            flat["warnings"].extend(v)
        else:
            flat[k] = v

    # --- Fallbacks ---
    flat = apply_fallbacks(flat)

    # --- Merge final fields ---
    flat = build_final_fields(flat)

    flat["timestamp"] = pd.Timestamp.now("UTC").isoformat()
    return flat


def process_row(row, candidates):
    """
    Worker function called in parallel.
    Handles identifier selection, resolution, fallback, warnings, etc.
    """

    # Convert pandas Series (iterrows) or tuple (itertuples) to dict
    if hasattr(row, "_asdict"):
        row_dict = row._asdict()
    else:
        row_dict = dict(row)

    selection = pick_best_identifier(row_dict, candidates)
    val = selection["identifier_value"]
    id_type = selection["identifier_type"]
    w = selection["warnings"]

    # Cache lookup
    key = (val, id_type)
    if key in CACHE:
        rec = CACHE[key].copy()
        rec["warnings"] = rec.get("warnings", []) + w
        return rec

    # No usable identifier
    if val is None:
        rec = {
            "input": None,
            "warnings": w,
            "timestamp": pd.Timestamp.now("UTC").isoformat()
        }
        CACHE[key] = rec
        return rec

    # Resolve identifier normally
    rec = resolve_identifier(val, id_type)
    rec["warnings"].extend(w)

    CACHE[key] = rec
    return rec

def resolve_dataframe(df: pd.DataFrame, return_wide: bool = False):
    """
    Resolve rows in parallel using ThreadPoolExecutor.

    Returns:
      - legacy_df (default): integrate_results_into_dataframe(...)
      - if return_wide=True: (legacy_df, wide_df) where wide_df is a raw wide join
        of input df + all fields returned by process_row().
    """
    from concurrent.futures import ThreadPoolExecutor
    from tqdm import tqdm

    candidates = get_candidate_identifier_columns(df)

    # Convert df to rows (tuples are faster)
    rows = list(df.itertuples(index=False))

    # Number of threads (tune if needed)
    max_workers = 8

    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for rec in tqdm(
            ex.map(lambda r: process_row(r, candidates), rows),
            total=len(rows),
            desc="Processing in parallel"
        ):
            results.append(rec)

    # 1) Existing/legacy output (unchanged)
    legacy_df = integrate_results_into_dataframe(df, results, identifier_col=None)

    if not return_wide:
        return legacy_df

    # 2) New: build a non-legacy "wide" dataframe from the raw per-row results
    def _rec_to_dict(rec):
        if rec is None:
            return {}
        if isinstance(rec, dict):
            return rec
        if hasattr(rec, "_asdict"):  # namedtuple-like
            return rec._asdict()
        try:
            return dict(rec)
        except Exception:
            # last resort: keep something stable rather than crashing
            return {"_raw_result": str(rec)}

    results_df = pd.DataFrame([_rec_to_dict(r) for r in results])

    # Deterministic row alignment (same order as input rows)
    wide_df = pd.concat([df.reset_index(drop=True), results_df.reset_index(drop=True)], axis=1)

    return legacy_df, wide_df

def cli():
    parser = argparse.ArgumentParser(description="Physical Properties Retrieval App")
    parser.add_argument("input_excel", help="Path to input Excel file")
    parser.add_argument("output_excel", help="Path to save output Excel file")
    parser.add_argument("--sheet", default=None, help="Sheet name or index. Default: first sheet.")
    parser.add_argument("--log", default="INFO")
    parser.add_argument(
        "--debug-install",
        action="store_true",
        help="Print installation and module path diagnostics."
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    import os
    from pathlib import Path
    from datetime import datetime

    # ----------------------------------------------------
    # Prevent system sleep (Windows)
    # ----------------------------------------------------
    try:
        import ctypes
        ES_CONTINUOUS = 0x80000000
        ES_SYSTEM_REQUIRED = 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(
            ES_CONTINUOUS | ES_SYSTEM_REQUIRED
        )
        logger.info("Sleep prevention activated.")
    except Exception as e:
        logger.warning(f"Could not set sleep prevention state: {e}")

    # ----------------------------------------------------
    # Debug mode
    # ----------------------------------------------------
    if args.debug_install:
        import inspect, physprops
        print("\n=== PhysProps Installation Debug ===")
        print("physprops package path:", physprops.__path__)
        print("main.py location:", inspect.getfile(cli))
        print("excel_io.load_excel:", inspect.getfile(load_excel))
        print("====================================\n")
        return

    # ----------------------------------------------------
    # Normalizing sheet argument
    # ----------------------------------------------------
    sheet = args.sheet if args.sheet not in (None, "", "None") else None

    # ----------------------------------------------------
    # Create output folder automatically (based on output_excel)
    # ----------------------------------------------------
    output_folder = os.path.dirname(args.output_excel)
    if output_folder and not os.path.exists(output_folder):
        os.makedirs(output_folder, exist_ok=True)
        logger.info(f"Created output directory: {output_folder}")

    # ----------------------------------------------------
    # Avoid overwriting existing files (fallback safety)
    # ----------------------------------------------------
    def safe_output_path(path: str) -> str:
        if not os.path.exists(path):
            return path

        base, ext = os.path.splitext(path)
        counter = 1
        new_path = f"{base} ({counter}){ext}"
        while os.path.exists(new_path):
            counter += 1
            new_path = f"{base} ({counter}){ext}"
        return new_path

    def timestamped_output_path(path: str) -> str:
        """
        Insert a timestamp before the file extension.
        Example: out.xlsx -> out__20260427_002139_123.xlsx
        """
        base, ext = os.path.splitext(path)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]  # milliseconds
        return f"{base}__{ts}{ext}"

    # ----------------------------------------------------
    # Compute timestamped legacy output path (do not overwrite)
    # ----------------------------------------------------
    final_output_path = safe_output_path(timestamped_output_path(args.output_excel))

    # Root folder for all “product” outputs
    root_dir = Path(final_output_path).resolve().parent

    # ----------------------------------------------------
    # Load & process (single pass)
    # ----------------------------------------------------
    df = load_excel(args.input_excel, sheet_name=sheet)

    # Expect resolve_dataframe to support return_wide=True
    out_legacy, out_wide = resolve_dataframe(df, return_wide=True)

    # ----------------------------------------------------
    # Ensure out_wide has canonical merge key: inchi_key
    # ----------------------------------------------------
    def _ensure_inchi_key(df_wide, df_legacy):
        df_wide = df_wide.copy()

        preferred_sources = [
            "inchi_key",
            "final_inchikey",
            "computed_inchikey",
            "inchikey",
            "InChIKey",
            "INCHI_KEY",
            "INCHIKEY",
        ]

        def _clean_series(s):
            s = s.astype(str).str.strip()
            s = s.replace({"": None, "None": None, "nan": None, "NaN": None})
            return s

        if "inchi_key" in df_wide.columns:
            df_wide["inchi_key"] = _clean_series(df_wide["inchi_key"])
            return df_wide

        for src in preferred_sources[1:]:
            if src in df_wide.columns:
                df_wide["inchi_key"] = _clean_series(df_wide[src])
                break

        if "inchi_key" not in df_wide.columns:
            df_leg = df_legacy.copy()
            for src in preferred_sources:
                if src in df_leg.columns:
                    df_leg["inchi_key"] = _clean_series(df_leg[src])
                    break

            if "inchi_key" in df_leg.columns and len(df_leg) == len(df_wide):
                df_wide["inchi_key"] = df_leg["inchi_key"]

        return df_wide



    out_wide = _ensure_inchi_key(out_wide, out_legacy)
    out_wide = enrich_hsp_columns(out_wide)

    # Run Henry enrichment FIRST
    try:
        out_wide = enrich_henry_columns(out_wide)
    except Exception as e:
        logger.warning(f"Henry enrichment skipped due to error: {e}")

    logger.info("[DEBUG] out_wide Henry nonnull: %s", {c: int(out_wide[c].notna().sum()) for c in ["henry_constant_mol_m3_Pa_25C","source_henry_constant"] if c in out_wide.columns})

    # THEN ensure experimental alias is filled from computed Henry if present
    if "henry_constant_mol_m3_Pa_25C" in out_wide.columns:
        if "experimental_henry_constant_mol_m3_pa" not in out_wide.columns:
            out_wide["experimental_henry_constant_mol_m3_pa"] = pd.NA
        out_wide["experimental_henry_constant_mol_m3_pa"] = (
            out_wide["experimental_henry_constant_mol_m3_pa"]
            .fillna(out_wide["henry_constant_mol_m3_Pa_25C"])
        )


    # ----------------------------------------------------
    # 1) Write non-legacy WIDE export (timestamped, do not overwrite)
    # ----------------------------------------------------
    wide_export_base = str(root_dir / "physprops_export_wide.xlsx")
    wide_export_path = safe_output_path(timestamped_output_path(wide_export_base))

    # Ensure sheet_name is defined (wide export reads a file; sheet_name can be None or 0)
    # If you don't support sheet selection, set it explicitly:
    sheet_name = None  # or 0, if you want first sheet always
    logger.info("HSP/HENRY cols in out_wide: %s", [c for c in out_wide.columns if ('henry' in c.lower() or 'hsp' in c.lower())])
    # Export MUST be based on out_wide (it contains Henry + HSP), so write a temp source file
    tmp_wide_source = safe_output_path(timestamped_output_path(str(root_dir / "_tmp_out_wide_source.xlsx")))
    save_excel(out_wide, tmp_wide_source)

    export_physprops_wide(tmp_wide_source, wide_export_path, sheet_name=sheet_name)
    logger.info(f"Saved non-legacy wide Excel file: {wide_export_path}")


    # ----------------------------------------------------
    # 2) Write LEGACY export (timestamped CLI output)
    # ----------------------------------------------------
    save_excel(out_legacy, final_output_path)
    logger.info(f"Saved legacy Excel file: {final_output_path}")
    # ----------------------------------------------------
    wide_export_base = str(root_dir / "physprops_export_wide.xlsx")


    # ----------------------------------------------------
    # 3) Update/maintain canonical database (derived from WIDE export)
    # ----------------------------------------------------

    preferred_canonical_dir = CANONICAL_ROOT_DIR
    canonical_root = root_dir  # fallback default

    try:
        preferred_canonical_dir.mkdir(parents=True, exist_ok=True)

        probe = preferred_canonical_dir / ".physprops_write_probe.tmp"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)

        canonical_root = preferred_canonical_dir
    except Exception as e:
        logger.warning(
            f"Preferred canonical dir not usable ({preferred_canonical_dir}); "
            f"falling back to output root_dir ({root_dir}). Reason: {e}"
        )

    
    local_root = os.getenv("CANONICAL_DB_LOCAL_ROOT")
    if local_root:
        canonical_db_path = Path(local_root) / "canonical_physchemprops.xlsx"
    else:
        canonical_db_path = canonical_root / "canonical_physchemprops.xlsx"

    canonical_audit_path = canonical_root / "canonical_audit_physprops.xlsx"

    logger.info(f"Canonical root chosen: {canonical_root}")
    logger.info(f"Canonical DB path: {canonical_db_path}")
    logger.info(f"Canonical audit path: {canonical_audit_path}")



    try:
        canonical_feed = out_wide.copy()

        schema_json_path = canonical_root / "canonical_schema.json"
        rejected_path = canonical_root / "canonical_physchemprops.rejected_physprops.xlsx"

        allowlist = load_or_init_allowlist(
            schema_json_path,
            canonical_xlsx_path=canonical_db_path if canonical_db_path.exists() else None,
            incoming_columns=canonical_feed.columns
        )

        logger.info(f"[DEBUG] canonical_feed has inchi_key={'inchi_key' in canonical_feed.columns}")
        logger.info(f"[DEBUG] canonical_feed cols sample={list(canonical_feed.columns)[:30]}")
        logger.info(f"[DEBUG] schema_json exists={schema_json_path.exists()} ; canonical_db exists={canonical_db_path.exists()}")

        logger.info("[DEBUG] canonical_feed HSP/HENRY nonnull: %s", {
            c: int(canonical_feed[c].notna().sum()) for c in [
                "experimental_hsp_delta_d_mpa05",
                "computed_hsp_delta_d_mpa05",
                "source_hsp",
                "source_hsp_computed",
                "henry_constant_mol_m3_Pa_25C",
                "log_henry_constant_mol_m3_Pa_25C",
                "experimental_henry_constant_mol_m3_pa",
                "source_henry_constant",
            ] if c in canonical_feed.columns
        })

        incoming, rejected = sanitize_outgoing(
            canonical_feed,
            tool_name="physprops",
            allowlist=allowlist
        )

        if "inchi_key" not in allowlist:
            raise ValueError(f"Schema allowlist missing 'inchi_key': {schema_json_path}")

        if incoming is None or incoming.empty:
            logger.warning("Canonical update skipped: no valid rows with a valid inchi_key after sanitization.")
            merged_rows = 0
        else:
            # First run: create canonical DB directly from incoming
            if not canonical_db_path.exists():
                write_xlsx_atomic(incoming, str(canonical_db_path), sheet_name="canonical",min_size_bytes=50_000)  # 50KB minimum to avoid zero-byte files
                merged_rows = len(incoming)
                logger.info(f"Created canonical DB (first run): {canonical_db_path} (rows={merged_rows})")
            else:
                existing = read_xlsx(canonical_db_path, sheet_name="canonical")
                merged = upsert_canonical(
                    existing=existing,
                    incoming=incoming,
                    tool_name="physprops",
                    allowlist=allowlist
                )
                write_xlsx_atomic(merged, str(canonical_db_path), sheet_name="canonical",min_size_bytes=50_000)  # 50KB minimum to avoid zero-byte files
                merged_rows = len(merged)
                logger.info(f"Updated canonical DB: {canonical_db_path} (rows={merged_rows})")                
                backup_dir = canonical_root / "backups"
                backup_dir.mkdir(parents=True, exist_ok=True)
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = backup_dir / f"canonical_physchemprops__{stamp}.xlsx"
                shutil.copy2(str(canonical_db_path), str(backup_path))
                logger.info(f"[OK] Canonical DB backup written: {backup_path}")

        # Rejected rows
        if rejected is not None and not rejected.empty:
            write_xlsx_atomic(rejected, str(rejected_path), sheet_name="rejected")
            logger.warning(f"Rejected rows written: {rejected_path} (rows={len(rejected)})")
            rejected_rows = len(rejected)
        else:
            logger.info("No rejected rows produced in this run.")
            rejected_rows = 0

        # Tool-specific audit (overwrite each run)
        audit_df = pd.DataFrame([{
            "tool": "PhysProps",
            "timestamp_utc": pd.Timestamp.now("UTC").isoformat(),
            "input_file": str(Path(args.input_excel).resolve()),
            "wide_export_file": str(Path(wide_export_path).resolve()),
            "legacy_export_file": str(Path(final_output_path).resolve()),
            "rows_wide": int(len(out_wide)),
            "rows_legacy": int(len(out_legacy)),
            "rows_incoming_valid": int(len(incoming)) if incoming is not None else 0,
            "rows_rejected": int(rejected_rows),
            "rows_canonical_after": int(merged_rows),
            "canonical_db_path": str(Path(canonical_db_path).resolve()),
            "schema_json_path": str(Path(schema_json_path).resolve()),
            "rejected_path": str(Path(rejected_path).resolve()),
        }])

        write_xlsx_atomic(audit_df, str(canonical_audit_path), sheet_name="audit")
        logger.info(f"Wrote canonical audit: {canonical_audit_path}")

    except Exception:
        logger.exception("Canonical update failed (wide+legacy outputs still written)")

    # Post-write verification (audit-friendly)
    db_exists = Path(canonical_db_path).exists()
    audit_exists = Path(canonical_audit_path).exists()
    logger.info(f"Canonical DB exists after write: {db_exists}")
    logger.info(f"Canonical audit exists after write: {audit_exists}")

    dbp = Path(canonical_db_path)
    if dbp.exists():
        logger.info(f"Canonical DB size: {dbp.stat().st_size} bytes")
