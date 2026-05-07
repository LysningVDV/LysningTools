# canonical_common/cas_registry.py
from __future__ import annotations

import json
import os
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd


# -----------------------------
# Defaults / schema
# -----------------------------

DEFAULT_DB2_COLUMNS: List[str] = [
    "cas_input",
    "cas_number_normalized",
    "cas_status",  # valid / invalid / repaired / ambiguous / mixture / uvcb / unresolved
    "inchi_key",
    "inchi",
    "smiles",
    "resolver_source",
    "resolver_confidence",
    "resolution_timestamp_utc",
    "evidence",
    "notes",
]

REGISTRY_SHEET = "registry"
AUDIT_SHEET = "audit"
REJECTED_SHEET = "rejected"


def _utc_now_iso() -> str:
    # Consistent with your existing usage patterns (pd.Timestamp.now("UTC").isoformat()).
    return pd.Timestamp.now("UTC").isoformat()


def _ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _read_json(path: Path) -> Dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, obj: Dict) -> None:
    _ensure_parent_dir(path)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True), encoding="utf-8")


def _coerce_str_or_empty(x) -> str:
    if pd.isna(x):
        return ""
    s = str(x).strip()
    if s.lower() in {"nan", "none", "null"}:
        return ""
    return s


def _normalize_inchikey(x) -> str:
    s = _coerce_str_or_empty(x)
    return s.upper()


def _clean_df_to_allowlist(df: pd.DataFrame, allowlist: List[str]) -> pd.DataFrame:
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=allowlist)

    out = df.copy()
    # Ensure all allowlist columns exist
    for c in allowlist:
        if c not in out.columns:
            out[c] = ""
    # Drop non-allowlisted columns deterministically
    out = out.loc[:, allowlist].copy()

    # Normalize critical fields
    out["cas_input"] = out["cas_input"].map(_coerce_str_or_empty)
    out["cas_number_normalized"] = out["cas_number_normalized"].map(_coerce_str_or_empty)
    out["cas_status"] = out["cas_status"].map(_coerce_str_or_empty).str.lower()
    out["inchi_key"] = out["inchi_key"].map(_normalize_inchikey)
    out["inchi"] = out["inchi"].map(_coerce_str_or_empty)
    out["smiles"] = out["smiles"].map(_coerce_str_or_empty)
    out["resolver_source"] = out["resolver_source"].map(_coerce_str_or_empty)
    out["resolver_confidence"] = pd.to_numeric(out["resolver_confidence"], errors="coerce")
    out["resolution_timestamp_utc"] = out["resolution_timestamp_utc"].map(_coerce_str_or_empty)
    out["evidence"] = out["evidence"].map(_coerce_str_or_empty)
    out["notes"] = out["notes"].map(_coerce_str_or_empty)

    # Fill missing timestamp if any key fields exist
    mask_has_any = (
        out["cas_number_normalized"].astype(bool)
        | out["inchi_key"].astype(bool)
        | out["cas_input"].astype(bool)
    )
    out.loc[mask_has_any & (out["resolution_timestamp_utc"] == ""), "resolution_timestamp_utc"] = _utc_now_iso()

    # Normalize statuses (keep your vocabulary, but enforce known ones when possible)
    known = {"valid", "invalid", "repaired", "ambiguous", "mixture", "uvcb", "unresolved"}
    out.loc[~out["cas_status"].isin(known) & (out["cas_status"] != ""), "cas_status"] = "unresolved"

    return out


# -----------------------------
# Allowlist loader / initializer
# -----------------------------

def load_or_init_allowlist(schema_json_db2: Path) -> List[str]:
    """
    Loads allowlist columns from Canonical_DB/cas_registry_schema.json.
    If missing, creates a minimal schema JSON with DEFAULT_DB2_COLUMNS.
    """
    schema_json_db2 = Path(schema_json_db2)

    if not schema_json_db2.exists():
        schema = {
            "name": "cas_registry_schema",
            "version": 1,
            "allowlist_columns": DEFAULT_DB2_COLUMNS,
            "sheet_name": REGISTRY_SHEET,
            "notes": "DB2 CAS Registry schema allowlist. DB1 remains authoritative keyed by inchi_key.",
            "created_utc": _utc_now_iso(),
        }
        _write_json(schema_json_db2, schema)
        return list(DEFAULT_DB2_COLUMNS)

    schema = _read_json(schema_json_db2)
    cols = schema.get("allowlist_columns", [])
    if not cols:
        cols = list(DEFAULT_DB2_COLUMNS)
        schema["allowlist_columns"] = cols
        schema["version"] = int(schema.get("version", 1)) + 1
        schema["updated_utc"] = _utc_now_iso()
        _write_json(schema_json_db2, schema)

    # Enforce deterministic order
    return list(cols)


# -----------------------------
# Excel read/write (atomic)
# -----------------------------

def read_registry_excel(
    registry_xlsx: Path,
    allowlist: List[str],
    sheet_name: str = REGISTRY_SHEET,
) -> pd.DataFrame:
    """
    Reads cas_registry.xlsx from the 'registry' sheet.
    If missing: returns empty DF with allowlist columns.
    If sheet missing: falls back to first sheet.
    """
    registry_xlsx = Path(registry_xlsx)
    if not registry_xlsx.exists():
        return pd.DataFrame(columns=allowlist)

    try:
        df = pd.read_excel(registry_xlsx, sheet_name=sheet_name, engine="openpyxl")
    except ValueError:
        # sheet not found -> first sheet fallback
        df = pd.read_excel(registry_xlsx, sheet_name=0, engine="openpyxl")

    return _clean_df_to_allowlist(df, allowlist)


def _write_xlsx_atomic_multi(
    path: Path,
    sheets: Dict[str, pd.DataFrame],
    min_bytes: int = 1024,
) -> None:
    """
    Self-contained atomic writer (multi-sheet).
    Mirrors your pattern: write temp -> size check -> os.replace.
    """
    path = Path(path)
    _ensure_parent_dir(path)
    tmp = path.with_suffix(path.suffix + ".tmp")

    with pd.ExcelWriter(tmp, engine="openpyxl") as xlw:
        for sheet, df in sheets.items():
            df.to_excel(xlw, sheet_name=sheet, index=False)

    size = tmp.stat().st_size if tmp.exists() else 0
    if size < min_bytes:
        raise IOError(f"Refusing to replace {path} with tiny temp file ({size} bytes).")

    os.replace(tmp, path)


def write_registry_excel_atomic(
    registry_xlsx: Path,
    registry_df: pd.DataFrame,
    sheet_name: str = REGISTRY_SHEET,
) -> None:
    """
    Writes local cas_registry.xlsx as a single-sheet workbook, atomically.
    """
    registry_xlsx = Path(registry_xlsx)
    _write_xlsx_atomic_multi(registry_xlsx, {sheet_name: registry_df})


def write_audit_workbook_atomic(
    audit_xlsx: Path,
    audit_df: pd.DataFrame,
    rejected_df: pd.DataFrame,
) -> None:
    """
    Writes governance audit workbook with sheets: 'audit' and 'rejected', atomically.
    """
    audit_xlsx = Path(audit_xlsx)
    _write_xlsx_atomic_multi(audit_xlsx, {AUDIT_SHEET: audit_df, REJECTED_SHEET: rejected_df})


# -----------------------------
# Conflict policy & upsert
# -----------------------------

@dataclass(frozen=True)
class UpsertResult:
    updated_registry: pd.DataFrame
    audit: pd.DataFrame
    rejected: pd.DataFrame


def _registry_key_columns() -> Tuple[str, str]:
    # Composite key supports one-to-many CAS -> multiple InChIKeys
    return ("cas_number_normalized", "inchi_key")


def _is_joinable_to_db1(row: pd.Series) -> bool:
    # mixtures/uvcb/unresolved typically have no inchi_key
    if not row.get("inchi_key"):
        return False
    status = (row.get("cas_status") or "").lower()
    if status in {"mixture", "uvcb"}:
        return False
    return True


def upsert_registry(
    existing: pd.DataFrame,
    incoming: pd.DataFrame,
    allowlist: List[str],
    conflict_policy: str = "mark_ambiguous_keep_both",
) -> UpsertResult:
    """
    Deterministic upsert with conflict detection.

    Rules (MVP):
    - Key is (cas_number_normalized, inchi_key).
    - A CAS may map to multiple inchi_keys: keep all mappings.
    - If a new mapping introduces a second distinct inchi_key for same CAS:
        -> mark all joinable rows for that CAS as cas_status='ambiguous'
        -> record audit event
    - Never silently overwrite a mismatching mapping:
        - if same key, we only *fill blanks* and/or *upgrade confidence* and *refresh timestamp*.
    - Mixture/UVCB:
        - keep cas_status=mixture/uvcb, leave inchi_key empty, do not join to DB1
    - Rejected rows:
        - missing cas_number_normalized OR cas_status=invalid with no meaningful content, etc.
    """
    existing = _clean_df_to_allowlist(existing, allowlist)
    incoming = _clean_df_to_allowlist(incoming, allowlist)

    # Reject rows that cannot be governed
    rejected_reasons = []
    keep_mask = []
    for idx, r in incoming.iterrows():
        casn = r["cas_number_normalized"]
        status = r["cas_status"]
        if not casn:
            rejected_reasons.append("missing cas_number_normalized")
            keep_mask.append(False)
            continue
        if status == "invalid":
            # still store invalid if you want traceability? MVP chooses to reject invalid from registry DB2.
            rejected_reasons.append("cas_status=invalid")
            keep_mask.append(False)
            continue
        keep_mask.append(True)
        rejected_reasons.append("")

    rejected = incoming.loc[[not k for k in keep_mask]].copy()
    if len(rejected) > 0:
        rejected["rejected_reason"] = [r for r, k in zip(rejected_reasons, keep_mask) if not k]
        rejected["rejected_timestamp_utc"] = _utc_now_iso()

    incoming = incoming.loc[keep_mask].copy()

    # Prepare audit log
    audit_rows: List[Dict] = []

    k1, k2 = _registry_key_columns()

    # Index existing by composite key for fast deterministic updates
    def _make_composite_key(df: pd.DataFrame, k1: str, k2: str) -> pd.Series:
        base = df[[k1, k2]].fillna("").astype(str)

        # If empty, return an empty Series with the right index
        if len(base) == 0:
            return pd.Series([], index=df.index, dtype="string")

        key = base.agg("||".join, axis=1)

        # Defensive: in some pandas edge cases agg can return a DataFrame
        if isinstance(key, pd.DataFrame):
            key = key.iloc[:, 0]

        return key.astype("string")

    existing = existing.copy()
    incoming = incoming.copy()

    existing["_key"] = _make_composite_key(existing, k1, k2)
    incoming["_key"] = _make_composite_key(incoming, k1, k2)

    existing_by_key = {k: i for i, k in enumerate(existing["_key"].tolist())}

    def merge_row(existing_row: pd.Series, inc_row: pd.Series) -> pd.Series:
        out = existing_row.copy()
        # Fill blanks from incoming
        for c in allowlist:
            if c in {k1, k2}:
                continue
            if (not _coerce_str_or_empty(out.get(c))) and _coerce_str_or_empty(inc_row.get(c)):
                out[c] = inc_row[c]

        # Confidence: keep max
        try:
            ex_conf = float(out.get("resolver_confidence")) if not pd.isna(out.get("resolver_confidence")) else None
        except Exception:
            ex_conf = None
        try:
            in_conf = float(inc_row.get("resolver_confidence")) if not pd.isna(inc_row.get("resolver_confidence")) else None
        except Exception:
            in_conf = None

        if in_conf is not None and (ex_conf is None or in_conf > ex_conf):
            out["resolver_confidence"] = in_conf
            out["resolver_source"] = inc_row.get("resolver_source", out.get("resolver_source", ""))

        # Timestamp: prefer latest non-empty
        in_ts = _coerce_str_or_empty(inc_row.get("resolution_timestamp_utc"))
        ex_ts = _coerce_str_or_empty(out.get("resolution_timestamp_utc"))
        if in_ts and (not ex_ts or in_ts > ex_ts):
            out["resolution_timestamp_utc"] = in_ts

        # Evidence/notes: append (deterministic)
        in_ev = _coerce_str_or_empty(inc_row.get("evidence"))
        if in_ev and in_ev not in _coerce_str_or_empty(out.get("evidence")):
            out["evidence"] = (f"{_coerce_str_or_empty(out.get('evidence'))} | {in_ev}").strip(" |")

        in_notes = _coerce_str_or_empty(inc_row.get("notes"))
        if in_notes and in_notes not in _coerce_str_or_empty(out.get("notes")):
            out["notes"] = (f"{_coerce_str_or_empty(out.get('notes'))} | {in_notes}").strip(" |")

        return out

    # Apply incoming changes
    for _, inc in incoming.iterrows():
        key = inc["_key"]
        if key in existing_by_key:
            # Update in-place, non-destructively
            i = existing_by_key[key]
            before = existing.loc[i].copy()
            existing.loc[i] = merge_row(existing.loc[i], inc)

            audit_rows.append({
                "event": "update_existing_mapping",
                "timestamp_utc": _utc_now_iso(),
                "cas_number_normalized": inc[k1],
                "inchi_key": inc[k2],
                "details": "Filled blanks / upgraded confidence / refreshed timestamp (non-destructive).",
            })
        else:
            # New mapping row
            new_row = {c: inc.get(c, "") for c in allowlist}
            existing = pd.concat([existing, pd.DataFrame([new_row])], ignore_index=True)

            audit_rows.append({
                "event": "insert_new_mapping",
                "timestamp_utc": _utc_now_iso(),
                "cas_number_normalized": inc[k1],
                "inchi_key": inc[k2],
                "details": "Inserted new CAS→InChIKey mapping row.",
            })

    # Conflict detection per CAS: if >1 distinct non-empty inchi_key for same CAS, mark ambiguous
    # Only consider joinable mappings (inchi_key present and not mixture/uvcb)
    existing = _clean_df_to_allowlist(existing.drop(columns=["_key"], errors="ignore"), allowlist)

    # Build per-CAS set of inchi_keys
    grp = existing.groupby("cas_number_normalized", dropna=False)
    for casn, sub in grp:
        if not _coerce_str_or_empty(casn):
            continue
        joinable = sub[sub.apply(_is_joinable_to_db1, axis=1)]
        iks = sorted(set([_normalize_inchikey(x) for x in joinable["inchi_key"].tolist() if _normalize_inchikey(x)]))
        if len(iks) >= 2 and conflict_policy == "mark_ambiguous_keep_both":
            # Mark joinable rows for this CAS as ambiguous, preserve mixture/uvcb rows unchanged.
            mask = (existing["cas_number_normalized"] == casn) & existing.apply(_is_joinable_to_db1, axis=1)
            existing.loc[mask, "cas_status"] = "ambiguous"

            audit_rows.append({
                "event": "cas_conflict_mark_ambiguous",
                "timestamp_utc": _utc_now_iso(),
                "cas_number_normalized": casn,
                "inchi_key": "",
                "details": f"CAS maps to multiple InChIKeys: {', '.join(iks)}. Marked joinable rows as ambiguous; retained all mappings.",
            })

    # Deterministic sort: CAS, status, inchi_key, timestamp
    existing["resolver_confidence"] = pd.to_numeric(existing["resolver_confidence"], errors="coerce")
    existing = existing.sort_values(
        by=["cas_number_normalized", "cas_status", "inchi_key", "resolution_timestamp_utc"],
        kind="mergesort",
        na_position="last",
    ).reset_index(drop=True)

    audit = pd.DataFrame(audit_rows)
    if len(audit) == 0:
        audit = pd.DataFrame(columns=["event", "timestamp_utc", "cas_number_normalized", "inchi_key", "details"])

    return UpsertResult(updated_registry=existing, audit=audit, rejected=rejected)


# -----------------------------
# Exports
# -----------------------------

def export_registry_csv(registry_df: pd.DataFrame, csv_path: Path) -> None:
    csv_path = Path(csv_path)
    _ensure_parent_dir(csv_path)
    registry_df.to_csv(csv_path, index=False, encoding="utf-8")


def export_registry_sqlite(registry_df: pd.DataFrame, sqlite_path: Path, table: str = "registry") -> None:
    sqlite_path = Path(sqlite_path)
    _ensure_parent_dir(sqlite_path)

    conn = sqlite3.connect(sqlite_path)
    try:
        registry_df.to_sql(table, conn, if_exists="replace", index=False)
        # Helpful indices for joins
        cur = conn.cursor()
        cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_cas ON {table}(cas_number_normalized);")
        cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_ik ON {table}(inchi_key);")
        conn.commit()
    finally:
        conn.close()


def backup_registry_to_onedrive(local_registry_xlsx: Path, backups_dir: Path) -> Path:
    """
    Timestamped copy to OneDrive governance backups after successful updates.
    """
    local_registry_xlsx = Path(local_registry_xlsx)
    backups_dir = Path(backups_dir)
    _ensure_parent_dir(backups_dir / "._keep")

    ts = pd.Timestamp.now("UTC").strftime("%Y%m%d_%H%M%S")
    dest = backups_dir / f"cas_registry__{ts}.xlsx"
    shutil.copy2(local_registry_xlsx, dest)
    return dest


# -----------------------------
# Path helpers (no new env vars)
# -----------------------------

def get_local_db_root() -> Path:
    root = os.environ.get("CANONICAL_DB_LOCAL_ROOT", "").strip()
    if not root:
        raise EnvironmentError("CANONICAL_DB_LOCAL_ROOT is not set.")
    return Path(root)


def get_db2_local_paths() -> Dict[str, Path]:
    root = get_local_db_root()
    return {
        "xlsx": root / "cas_registry.xlsx",
        "csv": root / "cas_registry.csv",
        "sqlite": root / "cas_registry.sqlite",
    }
