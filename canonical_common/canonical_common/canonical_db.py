from __future__ import annotations
import json
import re
import pandas as pd
import os
import time
import tempfile
from pandas.api.types import is_numeric_dtype, is_string_dtype, is_object_dtype
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple



# ----------------------------
# Validation / normalization
# ----------------------------

INCHIKEY_RE = re.compile(r"^[A-Z]{14}-[A-Z]{10}-[A-Z]$")

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def _as_str_or_na(x):
    if x is None:
        return pd.NA
    if isinstance(x, float) and pd.isna(x):
        return pd.NA
    s = str(x).strip()
    if s == "" or s.lower() in {"na", "n/a", "none", "null", "nan"}:
        return pd.NA
    return s

def normalize_inchikey(x):
    s = _as_str_or_na(x)
    if s is pd.NA:
        return pd.NA
    return str(s).strip().upper().replace(" ", "")

def is_valid_inchikey(x) -> bool:
    if x is None or x is pd.NA:
        return False
    return bool(INCHIKEY_RE.match(str(x)))

def coalesce_first_valid_inchikey(*vals):
    for v in vals:
        v = normalize_inchikey(v)
        if is_valid_inchikey(v):
            return v
    return pd.NA


# ----------------------------
# Schema governance
# ----------------------------

# Columns that must never appear in canonical (they cause ambiguity / drift)
BANNED_CANONICAL_COLS = {
    "computed_inchikey",
    "final_inchikey",
    "source_inchikey",
    "CAS_ID",
    "cas",
    "SMILES",
    "SchemaVersion",
}

# Rename legacy/synonym columns into canonical column names
RENAME_SYNONYMS = {
    # CAS/SMILES legacy
    "CAS_ID": "cas_number",
    "cas": "cas_number",
    "SMILES": "smiles",

    # InChIKey variants -> canonical inchi_key
    "InChIKey": "inchi_key",
    "INCHIKEY": "inchi_key",
    "INCHI_KEY": "inchi_key",
    "inchikey": "inchi_key",

    # InChI variants -> canonical inchi
    "InChI": "inchi",
    "INCHI": "inchi",

    #Henry constant variant -> canonical
    "experimental_henry_constant_mol_m3_pa": "henry_constant_mol_m3_Pa_25C",
}

def _make_unique_columns(cols):
    """Return a list of unique column names by suffixing duplicates: a, a__2, a__3, ..."""
    seen = {}
    out = []
    for c in cols:
        c0 = str(c)
        n = seen.get(c0, 0) + 1
        seen[c0] = n
        out.append(c0 if n == 1 else f"{c0}__{n}")
    return out


def _collapse_duplicate_columns(df):
    """
    If df has duplicate column names, collapse them into a single column by taking the
    first non-null value per row (left-to-right), then drop duplicates.
    """
    import pandas as pd

    if df.columns.is_unique:
        return df

    # For each duplicated name, combine left-to-right
    new_cols = []
    out = df.copy()

    for name in pd.Index(out.columns).unique():
        cols = [c for c in out.columns if c == name]
        if len(cols) == 1:
            new_cols.append(name)
            continue

        # Start from first, fillna from subsequent
        s = out[cols[0]]
        for c in cols[1:]:
            s = s.fillna(out[c])
        out[name] = s
        # Drop the extra duplicates
        for c in cols[1:]:
            out = out.drop(columns=c)

        new_cols.append(name)

    # Ensure still unique
    out.columns = pd.Index(out.columns)
    return out

def _apply_schema_normalization(cols: Sequence[str]) -> List[str]:
    """
    Non-destructive normalization:
    - apply rename synonyms (if defined)
    - strip whitespace
    - drop blanks
    - de-dup preserving order
    Does NOT filter/drop columns.
    """
    out: List[str] = []
    seen = set()
    for c in cols:
        c0 = str(c).strip()
        if not c0:
            continue
        # optional: apply rename synonyms if you still want canonicalized headers
        c0 = RENAME_SYNONYMS.get(c0, c0)
        if c0 not in seen:
            out.append(c0)
            seen.add(c0)
    return out


def load_or_init_allowlist(
    schema_path: Path,
    canonical_xlsx_path: Optional[Path] = None,
    incoming_columns: Optional[Sequence[str]] = None
) -> List[str]:
    if schema_path.exists():
        data = json.loads(schema_path.read_text(encoding="utf-8"))
        allowlist = data.get("allowlist", [])
        print("[DEBUG] allowlist raw len:", len(allowlist))
        allowlist2 = _apply_schema_normalization(allowlist)
        print("[DEBUG] allowlist normalized len:", len(allowlist2))
        # optionally: show what got removed
        removed = [c for c in allowlist if c not in set(allowlist2)]
        print("[DEBUG] removed by normalization (first 30):", removed[:30])
        return allowlist2

    # Initialize from canonical header if possible, otherwise from incoming columns
    if canonical_xlsx_path is not None and canonical_xlsx_path.exists():
        df = pd.read_excel(canonical_xlsx_path, engine="openpyxl")
        cols = list(df.columns)
    elif incoming_columns is not None:
        cols = list(incoming_columns)
    else:
        raise FileNotFoundError(
            "No canonical_schema.json exists, no canonical Excel exists, and no incoming_columns provided."
        )

    allowlist = _apply_schema_normalization(cols)

    payload = {
        "schema_version": "v1",
        "created_utc": utc_now_iso(),
        "allowlist": allowlist,
        "notes": "Auto-initialized allowlist; edit explicitly to change canonical schema.",
    }
    schema_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return allowlist


# ----------------------------
# Column allowlisting
# ----------------------------

def apply_allowlist(df: pd.DataFrame, allowlist: Sequence[str]) -> pd.DataFrame:
    df = df.copy()

    # prevent "cannot reindex on an axis with duplicate labels"
    df = _collapse_duplicate_columns_positional(df)

    # de-dup allowlist preserving order
    seen = set()
    allow = [c for c in allowlist if not (c in seen or seen.add(c))]

    existing_cols = [c for c in allow if c in df.columns]
    missing_cols  = [c for c in allow if c not in df.columns]

    final_cols = existing_cols + missing_cols

    return df.reindex(columns=final_cols)


    # Keep only allowlisted columns that already exist

# ----------------------------
# Identifier promotion
# ----------------------------

def promote_identifiers(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # rename synonyms early
    df = df.rename(columns={k: v for k, v in RENAME_SYNONYMS.items() if k in df.columns})

    # -------------------------
    # InChIKey promotion (authoritative primary key)
    # -------------------------
    for col in ["inchi_key", "final_inchikey", "computed_inchikey", "source_inchikey"]:
        if col not in df.columns:
            df[col] = pd.NA

    df["inchi_key"] = [
        coalesce_first_valid_inchikey(
            r["inchi_key"], r["final_inchikey"], r["computed_inchikey"], r["source_inchikey"]
        )
        for _, r in df[["inchi_key", "final_inchikey", "computed_inchikey", "source_inchikey"]].iterrows()
    ]

    # -------------------------
    # InChI promotion (canonical inchi string; not key)
    # -------------------------
    for col in ["inchi", "final_inchi", "computed_inchi", "source_inchi"]:
        if col not in df.columns:
            df[col] = pd.NA

    def _norm_inchi(x):
        s = _as_str_or_na(x)
        return pd.NA if s is pd.NA else str(s).strip()

    vals = []
    sub = df[["inchi", "final_inchi", "computed_inchi", "source_inchi"]]
    for _, r in sub.iterrows():
        v = _norm_inchi(r["inchi"])
        if v is pd.NA:
            v = _norm_inchi(r["final_inchi"])
        if v is pd.NA:
            v = _norm_inchi(r["computed_inchi"])
        if v is pd.NA:
            v = _norm_inchi(r["source_inchi"])
        vals.append(v)
    df["inchi"] = vals

    # -------------------------
    # CAS promotion into cas_number
    # -------------------------
    if "cas_number" not in df.columns:
        df["cas_number"] = pd.NA
    if "cas" in df.columns:
        df["cas_number"] = df["cas_number"].fillna(df["cas"])
    if "CAS_ID" in df.columns:
        df["cas_number"] = df["cas_number"].fillna(df["CAS_ID"])
    df["cas_number"] = df["cas_number"].map(_as_str_or_na)

    # -------------------------
    # SMILES promotion into canonical 'smiles'
    # -------------------------
    for col in ["smiles", "final_smiles", "computed_smiles", "source_smiles", "identifier_type", "normalized_input"]:
        if col not in df.columns:
            df[col] = pd.NA

    def _norm_smiles(x):
        s = _as_str_or_na(x)
        return pd.NA if s is pd.NA else str(s).strip()

    # Priority: smiles > final_smiles > computed_smiles > source_smiles
    # Fallback: normalized_input ONLY if identifier_type indicates SMILES
    sm = []
    for _, r in df[["smiles", "final_smiles", "computed_smiles", "source_smiles", "identifier_type", "normalized_input"]].iterrows():
        v = _norm_smiles(r["smiles"])
        if v is pd.NA:
            v = _norm_smiles(r["final_smiles"])
        if v is pd.NA:
            v = _norm_smiles(r["computed_smiles"])
        if v is pd.NA:
            v = _norm_smiles(r["source_smiles"])

        if v is pd.NA:
            it = "" if r["identifier_type"] is pd.NA else str(r["identifier_type"]).strip().lower()
            if it in {"smiles", "smile"}:
                v = _norm_smiles(r["normalized_input"])

        sm.append(v)

    df["smiles"] = sm

    # -------------------------
    # name_preferred normalization
    # -------------------------
    if "name_preferred" in df.columns:
        df["name_preferred"] = df["name_preferred"].map(_as_str_or_na)

    return df


# ----------------------------
# Deterministic deduplication
# ----------------------------

def _best_merge_group(rows: pd.DataFrame) -> pd.Series:
    """
    Deterministically merge multiple rows for the same inchi_key:
    - order by timestamp_updated (or timestamp) desc, then non-null count desc, then row order asc
    - take first row as base; fill NAs from subsequent rows
    """
    r = rows.copy()

    # stable row order for tie-breaking
    if "_row_order" not in r.columns:
        r["_row_order"] = range(len(r))

    ts_col = "timestamp_updated" if "timestamp_updated" in r.columns else ("timestamp" if "timestamp" in r.columns else None)
    if ts_col:
        r["_ts"] = pd.to_datetime(r[ts_col], errors="coerce", utc=True)
    else:
        r["_ts"] = pd.NaT

    r["_nn"] = r.notna().sum(axis=1)

    r = r.sort_values(by=["_ts", "_nn", "_row_order"], ascending=[False, False, True], kind="mergesort")

    merged = r.iloc[0].copy()
    for i in range(1, len(r)):
        row = r.iloc[i]
        na_mask = merged.isna()
        merged.loc[na_mask] = row.loc[na_mask]

    merged = merged.drop(labels=[c for c in ["_ts", "_nn", "_row_order"] if c in merged.index])
    return merged


def _collapse_duplicate_columns_positional(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse duplicate column labels: first non-null wins left-to-right (positional)."""
    if df.columns.is_unique:
        return df

    col_list = list(df.columns)
    collapsed = {}
    for name in pd.Index(col_list).unique():
        idxs = [i for i, c in enumerate(col_list) if c == name]
        if len(idxs) == 1:
            collapsed[name] = df.iloc[:, idxs[0]]
        else:
            s = df.iloc[:, idxs[0]].copy()
            for j in idxs[1:]:
                s = s.fillna(df.iloc[:, j])
            collapsed[name] = s
    return pd.DataFrame(collapsed)


def dedupe_by_inchikey(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    if "inchi_key" not in df.columns:
        raise KeyError(
            "dedupe_by_inchikey: 'inchi_key' column missing. "
            f"Columns present: {list(df.columns)}"
        )

    if df.empty:
        # Nothing to dedupe; preserve schema/columns
        return df.reset_index(drop=True)

    if not df.columns.is_unique:
        collapsed = {}
        col_list = list(df.columns)

        for name in pd.Index(col_list).unique():
            idxs = [i for i, c in enumerate(col_list) if c == name]

            if len(idxs) == 1:
                collapsed[name] = df.iloc[:, idxs[0]]
            else:
                s = df.iloc[:, idxs[0]].copy()
                for j in idxs[1:]:
                    s = s.fillna(df.iloc[:, j])
                collapsed[name] = s

        df = pd.DataFrame(collapsed)


    # Deterministic row order so "first row wins" is stable
    df["_row_order"] = range(len(df))

    # Keep only valid keys
    df = df[df["inchi_key"].map(is_valid_inchikey)].copy()

    if df.empty:
        return df.drop(columns=["_row_order"], errors="ignore").reset_index(drop=True)

    merged_rows = []
    for ik, grp in df.groupby("inchi_key", sort=True):
        grp_sorted = grp.sort_values("_row_order", kind="mergesort")

        merged = grp_sorted.iloc[0].copy()
        for j in range(1, len(grp_sorted)):
            merged = merged.combine_first(grp_sorted.iloc[j])

        merged_rows.append(merged.to_dict())

    out = pd.DataFrame(merged_rows)
    out = out.drop(columns=["_row_order"], errors="ignore")
    out = out.sort_values("inchi_key", kind="mergesort").reset_index(drop=True)

    return out

   

    # ---- Fix: ensure unique column labels (prevents InvalidIndexError downstream) ----
    # If you prefer "drop duplicates" instead of collapse, tell me; collapse is safer.


# ----------------------------
# Tool ownership (overwrite rules)
# ----------------------------

def owned_columns(tool_name: str, allowlist: Sequence[str]) -> List[str]:
    allow = list(allowlist)


    # Never considered "owned" for overwrite
    identity = {"inchi_key"}
    
    # Chem_Annotator should be allowed to write its descriptor columns
    if tool_name == "chem_annotator":
        # write everything allowlisted except identity
        return [c for c in allow if c not in identity]


    if tool_name == "physprops":
        owned = []
        for c in allow:
            if c.startswith(("computed_", "experimental_", "final_", "source_")):
                if c in {"source_primary", "source_secondary"}:
                    continue
                owned.append(c)
            if c.endswith("Count") or "Count_" in c:
                owned.append(c)
            if c in {
                "molecular_weight_g_mol",
                "logP_octanol_water",
                "topological_polar_surface_area_A2",
                "num_heavy_atoms",
                "vapor_pressure_Pa_25C",
                "log_vapor_pressure_Pa_25C",
                "henry_constant_mol_m3_Pa_25C",
                "log_henry_constant_mol_m3_Pa_25C",
                "boiling_point_C",
                "melting_point_C",
                "water_solubility_mg_L_25C",
                "log_water_solubility_mg_L_25C",
                "density_g_mL_25C",
            }:
                owned.append(c)
        # identifiers commonly supplied by resolver
        owned += ["cas_number", "smiles", "name_preferred"]
        return _dedup_preserve_order(owned)


    # default: overwrite nothing (safe)
    return []


def _dedup_preserve_order(seq: Sequence[str]) -> List[str]:
    out = []
    seen = set()
    for x in seq:
        if x not in seen:
            out.append(x)
            seen.add(x)
    return out


# ----------------------------
# Sanitize + upsert (main API)
# ----------------------------

FILL_ONLY_COLS = ["inchi"]  # per your governance choice


def sanitize_outgoing(
    df: pd.DataFrame,
    tool_name: str,
    allowlist: Sequence[str]
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Returns (clean_df, rejected_df):
      - clean_df: promoted identifiers, valid keys, deduped, allowlisted
      - rejected_df: rows with missing/invalid inchi_key (for audit)
    """
    df = df.copy()
    # Ensure unique column labels (duplicate labels can make df["inchi_key"] return a DataFrame)
    if not df.columns.is_unique:
        # Collapse duplicates by "first non-null wins" left-to-right, using positional indexing
        col_list = list(df.columns)
        collapsed = {}
        for name in pd.Index(col_list).unique():
            idxs = [i for i, c in enumerate(col_list) if c == name]
            if len(idxs) == 1:
                collapsed[name] = df.iloc[:, idxs[0]]
            else:
                s = df.iloc[:, idxs[0]].copy()
                for j in idxs[1:]:
                    s = s.fillna(df.iloc[:, j])
                collapsed[name] = s
        df = pd.DataFrame(collapsed)

    # ---- 0) Fast schema sanity (fail early & clearly) ----
    if "inchi_key" not in allowlist:
        raise ValueError("sanitize_outgoing: allowlist missing required 'inchi_key'")

    # ---- 1) Promote identifiers while all candidate columns still exist ----
    # (This should set canonical: inchi_key, inchi, smiles, cas_number, etc.)
    df = promote_identifiers(df)

    # ---- 2) Remove variant identifier columns that should not reach canonical ----
    # (Keeps only canonical identifiers + optional lineage you allow.)
    df = drop_variant_identifier_columns(df)

    # ---- 3) Validate primary key and split rejected rows ----
    if "inchi_key" not in df.columns:
        # This indicates promote_identifiers failed or renamed unexpectedly
        raise KeyError("sanitize_outgoing: 'inchi_key' missing after promote_identifiers")

    # --- Ensure inchi_key is a 1-D Series even if duplicate columns exist ---
    ik = df.get("inchi_key")

    # If there are duplicate 'inchi_key' columns, df.get returns a DataFrame
    # Collapse to first non-null per row (left-to-right).
    if isinstance(ik, pd.DataFrame):
        ik = ik.bfill(axis=1).iloc[:, 0]

    # Normalize for validation
    ik = ik.astype(str).str.strip().str.upper()
    ik = ik.replace({"": pd.NA, "NAN": pd.NA, "NONE": pd.NA})

    # Write back canonicalized key (keeps downstream logic consistent)
    df["inchi_key"] = ik

    # 1-D boolean mask aligned to df.index
    valid_mask = ik.map(is_valid_inchikey)
    valid_mask = valid_mask.fillna(False).astype(bool)

    # ALWAYS define rejected + incoming (even if empty)
    rejected = df.loc[~valid_mask].copy()
    incoming = df.loc[valid_mask].copy()
    df = incoming

    # If nothing left, return early (but keep schema columns in df)
    if df.empty:
        df = apply_allowlist(df, allowlist)
        return df.reset_index(drop=True), rejected.reset_index(drop=True)

    # ---- 4) Ensure timestamp_updated exists (do this after filtering invalid keys) ----
    now = utc_now_iso()
    if "timestamp_updated" in df.columns:
        df["timestamp_updated"] = df["timestamp_updated"].fillna(now)
    else:
        df["timestamp_updated"] = now

    # ---- 5) Dedupe within the outgoing batch (one row per inchi_key) ----
    # Your dedupe_by_inchikey should be deterministic.
    df = dedupe_by_inchikey(df)

    # ---- 6) Enforce allowlist last (stops column growth, stable order) ----
    df = apply_allowlist(df, allowlist)

    # ---- 7) Final guardrail ----
    if "inchi_key" not in df.columns:
        raise KeyError("sanitize_outgoing: 'inchi_key' missing after allowlist — schema is wrong.")

    return df.reset_index(drop=True), rejected.reset_index(drop=True)


from pandas.api.types import is_numeric_dtype

def upsert_canonical(
    existing: pd.DataFrame,
    incoming: pd.DataFrame,
    tool_name: str,
    allowlist: Sequence[str]
) -> pd.DataFrame:
    """
    Deterministic index-based upsert using inchi_key.
    Includes:
    - existing dedupe
    - incoming dedupe
    - fill-only columns (inchi)
    - tool-owned overwrite columns
    """
    existing = promote_identifiers(existing)
    incoming = promote_identifiers(incoming)

    existing = apply_allowlist(existing, allowlist)
    incoming = apply_allowlist(incoming, allowlist)

    # TEMP DEBUG (remove later): detect duplicate columns early
    dup_e = []
    dup_i = []
    if not existing.columns.is_unique:
        dup_e = sorted(set(existing.columns[existing.columns.duplicated()].tolist()))
    if not incoming.columns.is_unique:
        dup_i = sorted(set(incoming.columns[incoming.columns.duplicated()].tolist()))

    # print("[UPSERT] DUP existing:", dup_e[:30])
    # print("[UPSERT] DUP incoming:", dup_i[:30])

    existing = _collapse_duplicate_columns_positional(existing)
    incoming = _collapse_duplicate_columns_positional(incoming)

    existing = dedupe_by_inchikey(existing)
    incoming = dedupe_by_inchikey(incoming)

    ex = existing.set_index("inchi_key")
    inc = incoming.set_index("inchi_key")
    
    # Ensure unique columns to prevent inc.loc[:, c] returning a DataFrame for duplicated c
    ex = _collapse_duplicate_columns_positional(ex)
    inc = _collapse_duplicate_columns_positional(inc)

    # Add new keys
    new_keys = inc.index.difference(ex.index)
    if len(new_keys) > 0:
        ex = pd.concat([ex, inc.loc[new_keys]], axis=0)

    common_keys = inc.index.intersection(ex.index)

    # ---- Fill-only governance (inchi) ----
    for c in FILL_ONLY_COLS:
        if c not in ex.columns or c not in inc.columns:
            continue

        ex_val = ex.loc[common_keys, c]
        inc_val = inc.loc[common_keys, c]

        ex_missing = ex_val.isna() | (ex_val.astype(str).str.strip() == "")
        inc_present = inc_val.notna() & (inc_val.astype(str).str.strip() != "")

        mask = ex_missing & inc_present
        if mask.any():
            keys = mask.index[mask]  # robust boolean indexing
            ex.loc[keys, c] = inc.loc[keys, c]

    # ---- Tool-owned overwrites ----
    owned = owned_columns(tool_name, allowlist)

    # Only keep columns that actually exist in BOTH frames
    owned = [c for c in owned if c not in {"inchi_key"} and c not in FILL_ONLY_COLS]
    owned = [c for c in owned if (c in ex.columns and c in inc.columns)]


    for c in owned:
        mask = inc.loc[common_keys, c].notna()
        if not mask.any():
            continue

        keys = mask.index[mask]
        inc_vals = inc.loc[keys, c]

        # If inc_vals ever comes back as DataFrame (duplicate labels), collapse row-wise
        if isinstance(inc_vals, pd.DataFrame):
            inc_vals = inc_vals.bfill(axis=1).iloc[:, 0]

        # ---- KEY CHANGE: numeric columns stay numeric ----
        if is_numeric_dtype(ex[c]) and is_numeric_dtype(inc_vals):
            # safe numeric assignment into numeric destination
            ex.loc[keys, c] = pd.to_numeric(inc_vals, errors="coerce").to_numpy()
            continue

        # ---- non-numeric path (strings, arrow strings, mixed) ----
        if is_numeric_dtype(ex[c]) and not is_numeric_dtype(inc_vals):
            ex[c] = ex[c].astype("object")

        ex.loc[keys, c] = inc_vals.astype("object").to_numpy()


    # Always bump timestamp_updated for touched keys (optional, but helpful)
    if "timestamp_updated" in ex.columns:
        ex.loc[common_keys, "timestamp_updated"] = utc_now_iso()

    out = ex.reset_index()
    out = apply_allowlist(out, allowlist)
    out = out.sort_values("inchi_key", kind="mergesort").reset_index(drop=True)
    return out

# ----------------------------
# IO helpers
# ----------------------------

def read_xlsx(path: Path, sheet_name: str | int = 0) -> pd.DataFrame:
    return pd.read_excel(path, sheet_name=sheet_name, engine="openpyxl")

def write_xlsx(df: pd.DataFrame, path: Path, sheet_name: str = "canonical") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name=sheet_name)

def drop_variant_identifier_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Keep canonical: inchi_key, inchi, smiles, cas_number
    Keep lineage (optional): computed_inchi, final_inchi, source_inchi, computed_smiles, final_smiles, source_smiles
    Drop other identifier variants that can cause schema drift.
    """
    df = df.copy()

    keep = {
        "inchi_key", "inchi", "smiles", "cas_number",
        # lineage you explicitly accept
        "computed_inchi", "final_inchi", "source_inchi",
        "computed_smiles", "final_smiles", "source_smiles",
        "computed_inchikey", "final_inchikey", "source_inchikey",  # these will be banned by schema anyway
        "input", "normalized_input", "identifier_type",            # keep as input lineage (not canonical IDs)
    }

    drop = []
    for c in df.columns:
        cl = c.lower()
        if ("inchi" in cl or "inchikey" in cl) and c not in keep and c != "inchi_key":
            drop.append(c)
    if drop:
        df = df.drop(columns=drop, errors="ignore")
    return df

def resolve_canonical_paths(schema_root: Path) -> dict:
    local_root = os.getenv("CANONICAL_DB_LOCAL_ROOT")
    if local_root:
        db_root = Path(local_root)
    else:
        db_root = schema_root  # fallback

    return {
        "schema_path": schema_root / "canonical_schema.json",
        "db_path": db_root / "canonical_physchemprops.xlsx",
        "backup_dir": schema_root / "backups",
    }

def _acquire_lock(lock_path: Path, timeout_s: int = 120) -> None:
    start = time.time()
    while True:
        try:
            # exclusive create
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return
        except FileExistsError:
            if time.time() - start > timeout_s:
                raise TimeoutError(f"Timed out waiting for lock: {lock_path}")
            time.sleep(0.2)

def _release_lock(lock_path: Path) -> None:
    try:
        lock_path.unlink()
    except Exception:
        pass


def write_xlsx_atomic(df: pd.DataFrame, path: str, sheet_name: str = "Sheet1", min_size_bytes: int = 0) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    lock = path.with_suffix(path.suffix + ".lock")
    _acquire_lock(lock)
    tmp_path = None
    try:
        fd, tmp = tempfile.mkstemp(prefix=path.stem + "__", suffix=path.suffix, dir=str(path.parent))
        os.close(fd)
        tmp_path = Path(tmp)

        df.to_excel(tmp_path, index=False, engine="openpyxl", sheet_name=sheet_name)

        # ✅ validate temp BEFORE replacing final
        if min_size_bytes and tmp_path.stat().st_size < min_size_bytes:
            raise RuntimeError(f"Refusing suspiciously small temp Excel file: {tmp_path} ({tmp_path.stat().st_size} bytes)")

        os.replace(tmp_path, path)

    finally:
        _release_lock(lock)
        if tmp_path is not None and tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass