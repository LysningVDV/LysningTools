from __future__ import annotations

import html
import math
import re
import sqlite3
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List


# -----------------------------------------------------------------------------
# Local pinned version (matches your raw artifacts: henry-5.0.0.sql)
# -----------------------------------------------------------------------------
SANDER_HENRY_LOCAL_VERSION = "5.0.0"

# Folder layout (relative to this file):
#   Sander_henry/
#     sander_henry.py
#     raw/
#        henry-5.0.0.sql
#        cache/
#           henry-5.0.0.sqlite
RAW_DIR = Path(__file__).resolve().parent / "raw"
SQL_PATH = RAW_DIR / f"henry-{SANDER_HENRY_LOCAL_VERSION}.0.sql"
# Your tree shows henry-5.0.0.sql exactly; keep that exact name:
SQL_PATH_FALLBACK = RAW_DIR / f"henry-{SANDER_HENRY_LOCAL_VERSION}.sql"
CACHE_DIR = RAW_DIR / "cache"
SQLITE_PATH = CACHE_DIR / f"henry-{SANDER_HENRY_LOCAL_VERSION}.sqlite"


_HOMINUS_SUP_RE = re.compile(r"10<sup>(.*?)</sup>", re.IGNORECASE)

def _parse_hominus_to_float(x) -> float | None:
    """
    Convert Sander 'Hominus' strings to float.
    Handles HTML entities like '&times;' and '<sup>&#8722;6</sup>'.
    Returns None if parsing fails.
    """
    if x is None:
        return None
    s = str(x).strip()
    if not s:
        return None

    # Decode HTML entities: &times; -> ×, &#8722; -> −, etc.
    s = html.unescape(s)

    # Normalize unicode minus (U+2212) to ASCII minus
    s = s.replace("−", "-")

    # Common patterns:
    #  "1.1×10<sup>-6</sup>"
    #  "3.6×10<sup>-6</sup>"
    #  Sometimes without ×: "1.1x10<sup>-6</sup>"
    s = s.replace("&times;", "×")  # harmless if already unescaped
    s = s.replace("x10", "×10").replace("X10", "×10")

    m = _HOMINUS_SUP_RE.search(s)
    if m:
        # Extract exponent from the <sup>...</sup>
        exp_str = m.group(1).strip()
        exp_str = html.unescape(exp_str).replace("−", "-")
        try:
            exp = int(exp_str)
        except Exception:
            # if exponent isn't clean int, bail
            return None

        # Mantissa is everything before '×10<sup...'
        mantissa_part = s.split("×10<sup", 1)[0].strip()
        try:
            mantissa = float(mantissa_part)
        except Exception:
            return None
        return mantissa * (10.0 ** exp)

    # Fallback: plain float
    try:
        return float(s)
    except Exception:
        return None

# -----------------------------------------------------------------------------
# Helper: parse semantic version
# -----------------------------------------------------------------------------
def _parse_version_tuple(v: str) -> Tuple[int, int, int]:
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", v.strip())
    if not m:
        raise ValueError(f"Not a semantic version: {v!r}")
    return tuple(int(x) for x in m.groups())  # type: ignore


# -----------------------------------------------------------------------------
# Public metadata record (kept small; enrich.py builds the verbose source string)
# -----------------------------------------------------------------------------
@dataclass(frozen=True)
class SanderHenryRecord:
    henry_constant_mol_m3_Pa_25C: Optional[float]
    log_henry_constant_mol_m3_Pa_25C: Optional[float]
    source: str


@dataclass(frozen=True)
class SanderHenrySourceInfo:
    """
    Lightweight source info for audit strings.
    """
    version: str = SANDER_HENRY_LOCAL_VERSION
    source_name: str = "Sander Henry's law database"


# -----------------------------------------------------------------------------
# Optional: warning-only check for newer version (kept as stub; offline safe)
# -----------------------------------------------------------------------------
def check_for_new_sander_henry_version(
    local_version: str = SANDER_HENRY_LOCAL_VERSION,
    timeout_seconds: float = 2.0,
) -> Optional[str]:
    """
    Non-blocking check for a newer Sander Henry DB version.
    Currently returns None if offline/unavailable.
    """
    # Keep this function non-blocking and optional.
    try:
        import requests  # optional dependency
    except Exception:
        return None

    # If you later want to implement real checking, do it here.
    # For now: skip to keep deterministic.
    _ = (local_version, timeout_seconds, requests)
    return None


# -----------------------------------------------------------------------------
# Core: SQLite builder + schema autodetection + lookup by InChIKey
# -----------------------------------------------------------------------------
class SanderHenryDatabase:
    """
    Build/opens a local SQLite database from the shipped .sql file and provides
    lookup by InChIKey.

    Design goals:
    - Minimal assumptions about schema: autodetects relevant table/columns.
    - Deterministic and offline: uses local raw SQL artifact.
    - Safe: if anything fails, returns None rather than crashing callers.
    """

    def __init__(self, sqlite_path: Path = SQLITE_PATH, sql_path: Optional[Path] = None):
        self.sqlite_path = Path(sqlite_path)
        self.sql_path = Path(sql_path) if sql_path else self._default_sql_path()

        self._conn: Optional[sqlite3.Connection] = None
        self._schema: Optional[Dict[str, Any]] = None  # detected schema info

    def _default_sql_path(self) -> Path:
        if SQL_PATH.exists():
            return SQL_PATH
        return SQL_PATH_FALLBACK

    def _connect(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn

        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)

        # Build DB if missing OR empty/corrupt (0-byte / placeholder)
        if (not self.sqlite_path.exists()) or (self.sqlite_path.stat().st_size < 4096):
            self._build_sqlite_from_sql()


        self._conn = sqlite3.connect(str(self.sqlite_path))
        self._conn.row_factory = sqlite3.Row
        return self._conn

    def _build_sqlite_from_sql(self) -> None:
        """
        Build a local SQLite DB from the shipped Postgres-flavoured .sql dump.

        Your dump uses INSERT statements (not COPY), so the strategy is:
        - Execute statements one-by-one (so we can pinpoint failures).
        - Sanitize Postgres-only constructs that SQLite doesn't understand (SERIAL, CASCADE, sequences, constraints).
        """
        import re
        import sqlite3

        if not self.sql_path.exists():
            raise FileNotFoundError(f"Sander Henry SQL not found: {self.sql_path}")

        # Create fresh DB
        if self.sqlite_path.exists():
            try:
                self.sqlite_path.unlink()
            except Exception:
                pass

        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.sqlite_path))
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")

            def sanitize(stmt: str) -> str:
                s = stmt.strip()
                lines = []
                for ln in s.splitlines():
                    if ln.lstrip().startswith("--"):
                        continue
                    lines.append(ln)
                s = "\n".join(lines).strip()
                if not s:
                    return ""

                # Skip Postgres sequence-dependent statements (SQLite has no CURRVAL/NEXTVAL)
                if "currval(" in s.lower() or "nextval(" in s.lower():
                    return ""

                # ... keep the rest of your sanitize rules here ...

                # Remove Postgres-only CASCADE only for DROP TABLE statements (SQLite doesn't support it there)
                if re.match(r"(?is)^\s*DROP\s+TABLE\b", s):
                    # e.g. "DROP TABLE IF EXISTS foo CASCADE;" -> "DROP TABLE IF EXISTS foo;"
                    s = re.sub(r"(?i)\s+CASCADE\s*;", ";", s)
                    s = re.sub(r"(?i)\s+CASCADE\s*$", "", s)

                # Defensive cleanup: if any step left dangling FK actions, remove them
                s = re.sub(r"(?i)\bON\s+UPDATE\s*,", "", s)
                s = re.sub(r"(?i)\bON\s+DELETE\s*,", "", s)

                # Skip Postgres sequence machinery / setval (not needed for lookup)
                if re.match(r"(?is)^\s*CREATE\s+SEQUENCE\b", s):
                    return ""
                if re.match(r"(?is)^\s*ALTER\s+SEQUENCE\b", s):
                    return ""
                if "pg_catalog.setval" in s.lower():
                    return ""

                # Skip constraints added later (FK constraints are not required for lookup)
                if re.match(r"(?is)^\s*ALTER\s+TABLE\b.*\bADD\s+CONSTRAINT\b", s):
                    return ""

                # Convert SERIAL -> INTEGER (SQLite understands INTEGER PRIMARY KEY behaviour)
                s = re.sub(r"(?i)\bSERIAL\b", "INTEGER", s)

                # Optional: normalize INT -> INTEGER
                s = re.sub(r"(?i)\bINT\b", "INTEGER", s)

                return s.strip()

            # Execute statement-by-statement so failures are debuggable
            buf = []
            stmt_count = 0

            with self.sql_path.open("r", encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    # Skip Postgres dump comments (otherwise they can prefix real statements)
                    if line.lstrip().startswith("--"):
                        continue

                    buf.append(line)
                    joined = "".join(buf)
                    if sqlite3.complete_statement(joined):
                        stmt = joined
                        buf = []

                        stmt = sanitize(stmt)
                        if not stmt:
                            continue

                        stmt_count += 1
                        
                        try:
                            conn.executescript(stmt)
                        except Exception as e:
                            preview = stmt[:600].replace("\n", "\\n")
                            raise RuntimeError(
                                f"SQLite build failed at statement #{stmt_count}: {type(e).__name__}: {e}\n"
                                f"Statement preview: {preview}"
                            ) from e

            # Trailing statement (if any)
            if buf:
                stmt = sanitize("".join(buf))
                if stmt:
                    stmt_count += 1
                    conn.executescript(stmt)

            conn.commit()
        finally:
            conn.close()



    def _list_tables(self, conn: sqlite3.Connection) -> List[str]:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        return [r[0] for r in rows]

    def _table_columns(self, conn: sqlite3.Connection, table: str) -> List[str]:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        # PRAGMA table_info returns: cid, name, type, notnull, dflt_value, pk
        return [r[1] for r in rows]

    def _detect_schema(self) -> Dict[str, Any]:
        """
        Find:
        - table containing InChIKey column
        - constant column(s) for 25C (or nearest)
        - log constant column(s) for 25C (or nearest)
        """
        if self._schema is not None:
            return self._schema

        conn = self._connect()
        tables = self._list_tables(conn)

        # Candidate tables: have a column that looks like inchikey
        candidates = []
        for t in tables:
            cols = self._table_columns(conn, t)
            cols_l = [c.lower() for c in cols]
            if any("inchikey" in c or "inchi_key" in c for c in cols_l):
                candidates.append((t, cols))

        if not candidates:
            raise RuntimeError("No table with InChIKey column found in Henry SQLite DB.")

        # Pick best table: most columns (heuristic) to maximize chance of having the constants
        candidates.sort(key=lambda x: len(x[1]), reverse=True)
        table, cols = candidates[0]
        cols_l = [c.lower() for c in cols]

        # Identify the inchikey column name
        inchikey_col = None
        for c in cols:
            cl = c.lower()
            if "inchikey" in cl or "inchi_key" in cl:
                inchikey_col = c
                break
        if inchikey_col is None:
            raise RuntimeError("InChIKey column not detected despite candidate selection.")

        # Identify constant/log columns by heuristics
        # Prefer columns that mention 25C / 298 / 298k; else fallback to any 'henry' column.
        def pick_col(preds: List[str]) -> Optional[str]:
            for ptn in preds:
                for c in cols:
                    if ptn in c.lower():
                        return c
            return None

        # Try common patterns
        henry_col = pick_col(["25c", "298", "298k", "henry_constant", "henry"])
        log_col = pick_col(["log", "ln", "log_henry", "loghenry"])

        self._schema = {
            "table": table,
            "inchikey_col": inchikey_col,
            "henry_col": henry_col,
            "log_col": log_col,
            "cols": cols,
        }
        return self._schema

    def lookup_by_inchikey(self, inchi_key: str) -> Optional[SanderHenryRecord]:
        """
        Return Henry record for exact InChIKey match, or None.
        """
        if not inchi_key or not str(inchi_key).strip():
            return None

        ik = str(inchi_key).strip().upper()

        try:
            conn = self._connect()
            # Prefer the known schema (henry + species) when present:
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            tables_l = {t.lower() for t in tables}

            if "henry" in tables_l and "species" in tables_l:
                # Deterministic choice: take the first row by henry.id
                q = (
                    "SELECT h.Hominus "
                    "FROM henry h "
                    "JOIN species s ON s.id = h.species_id "
                    "WHERE UPPER(s.inchikey) = ? "
                    "ORDER BY h.id "
                    "LIMIT 1"
                )
                row = conn.execute(q, (ik,)).fetchone()
                if row is None:
                    return None

                hom = row["Hominus"] if isinstance(row, sqlite3.Row) else row[0]
                henry_val = _parse_hominus_to_float(hom)
                if henry_val is None:
                    return None

                log_val = math.log10(henry_val) if henry_val > 0 else None

                src = f"Sander Henry DB v{SANDER_HENRY_LOCAL_VERSION}; id=InChIKey={ik}"

                return SanderHenryRecord(
                    henry_constant_mol_m3_Pa_25C=henry_val,
                    log_henry_constant_mol_m3_Pa_25C=log_val,
                    source=src,
                )

            # Fallback to autodetection path (optional):
            schema = self._detect_schema()
            table = schema["table"]
            inchikey_col = schema["inchikey_col"]
            henry_col = schema["henry_col"]
            log_col = schema["log_col"]

            if henry_col is None and log_col is None:
                return None

            sel_cols = [inchikey_col]
            if henry_col is not None:
                sel_cols.append(henry_col)
            if log_col is not None and log_col not in sel_cols:
                sel_cols.append(log_col)

            q = f"SELECT {', '.join(sel_cols)} FROM {table} WHERE UPPER({inchikey_col}) = ? LIMIT 1"
            row = conn.execute(q, (ik,)).fetchone()
            if row is None:
                return None

            henry_val = _parse_hominus_to_float(row[henry_col]) if henry_col is not None else None
            log_val = None
            if log_col is not None:
                try:
                    log_val = float(row[log_col]) if row[log_col] is not None else None
                except Exception:
                    log_val = None
            if log_val is None and henry_val is not None and henry_val > 0:
                log_val = math.log10(henry_val)

            src = f"Sander Henry DB v{SANDER_HENRY_LOCAL_VERSION}; id=InChIKey={ik}"

            return SanderHenryRecord(
                henry_constant_mol_m3_Pa_25C=henry_val,
                log_henry_constant_mol_m3_Pa_25C=log_val,
                source=src,
            )
        except Exception as e:
            warnings.warn(f"Sander Henry lookup failed: {e}", RuntimeWarning)
            return None