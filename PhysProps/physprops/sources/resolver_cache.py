# physprops/sources/resolver_cache.py
import sqlite3, time
from pathlib import Path
from typing import Optional, Tuple

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS resolver_cache (
  resolver TEXT NOT NULL,            -- 'pubchem' etc.
  key_type TEXT NOT NULL,            -- 'cas'/'name'/'smiles'
  key_value TEXT NOT NULL,
  status TEXT NOT NULL,              -- success/not_found/bad_request/temp_error
  result TEXT,                       -- CID as text (or empty)
  http_status INTEGER,
  updated_utc INTEGER NOT NULL,
  PRIMARY KEY (resolver, key_type, key_value)
);
"""

class ResolverCache:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path, timeout=30) as con:
            con.execute("PRAGMA journal_mode=WAL;")
            con.execute(SCHEMA_SQL)

    def get(self, resolver: str, key_type: str, key_value: str) -> Optional[Tuple[str, Optional[str], Optional[int], int]]:
        with sqlite3.connect(self.path, timeout=30) as con:
            row = con.execute(
                "SELECT status, result, http_status, updated_utc FROM resolver_cache WHERE resolver=? AND key_type=? AND key_value=?",
                (resolver, key_type, key_value),
            ).fetchone()
        return row if row else None

    def put(self, resolver: str, key_type: str, key_value: str, status: str,
            result: Optional[str] = None, http_status: Optional[int] = None):
        now = int(time.time())
        with sqlite3.connect(self.path, timeout=30) as con:
            con.execute("PRAGMA journal_mode=WAL;")
            con.execute(
                "INSERT INTO resolver_cache(resolver,key_type,key_value,status,result,http_status,updated_utc) "
                "VALUES(?,?,?,?,?,?,?) "
                "ON CONFLICT(resolver,key_type,key_value) DO UPDATE SET "
                "status=excluded.status, result=excluded.result, http_status=excluded.http_status, updated_utc=excluded.updated_utc",
                (resolver, key_type, key_value, status, result, http_status, now),
            )