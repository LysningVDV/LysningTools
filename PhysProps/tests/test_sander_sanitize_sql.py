from pathlib import Path
import inspect
import pytest

from physprops.sources.Sander_henry.sander_henry import SanderHenryDatabase


def test_sander_henry_builds_sqlite_from_min_postgres_sql(tmp_path: Path):
    """
    Regression test for Postgres->SQLite import sanitization.

    It exercises:
    - DROP TABLE ... CASCADE;
    - SERIAL columns
    - FK constraints with ON UPDATE CASCADE (must not be broken)
    - CURRVAL(...) insert (must be skipped)
    """
    sig = inspect.signature(SanderHenryDatabase)
    if "sqlite_path" not in sig.parameters or "sql_path" not in sig.parameters:
        pytest.skip("SanderHenryDatabase constructor does not accept sqlite_path/sql_path overrides")

    # Define paths FIRST (so Pylance sees they exist)
    sql_path = tmp_path / "min_henry.sql"
    sqlite_path = tmp_path / "min_henry.sqlite"

    sql_path.write_text(
        "-- -*- mode: sql; sql-product: postgres; -*-\n"
        "DROP TABLE IF EXISTS species CASCADE;\n"
        "DROP TABLE IF EXISTS henry CASCADE;\n"
        "DROP TABLE IF EXISTS notes CASCADE;\n"
        "DROP TABLE IF EXISTS henry_notes CASCADE;\n"
        "\n"
        "CREATE TABLE notes (\n"
        "  id SERIAL PRIMARY KEY,\n"
        "  notelabel TEXT\n"
        ");\n"
        "CREATE TABLE species (\n"
        "  id SERIAL PRIMARY KEY,\n"
        "  inchikey TEXT\n"
        ");\n"
        "CREATE TABLE henry (\n"
        "  id SERIAL PRIMARY KEY,\n"
        "  Hominus TEXT,\n"
        "  species_id INT REFERENCES species(id) ON UPDATE CASCADE\n"
        ");\n"
        "CREATE TABLE henry_notes (\n"
        "  id SERIAL,\n"
        "  henry_id INT REFERENCES henry(id) ON UPDATE CASCADE,\n"
        "  notes_id INT REFERENCES notes(id) ON UPDATE CASCADE,\n"
        "  CONSTRAINT henry_notes_pkey PRIMARY KEY (henry_id, notes_id)\n"
        ");\n"
        "\n"
        "INSERT INTO species (inchikey) VALUES ('AAAAAAAAAAAAAA-UHFFFAOYSA-N');\n"
        "INSERT INTO henry (Hominus, species_id) VALUES ('1.23', 1);\n"
        "INSERT INTO notes (notelabel) VALUES ('moreTdep');\n"
        "INSERT INTO henry_notes (henry_id, notes_id) VALUES ((SELECT CURRVAL('henry_id_seq')), (SELECT id FROM notes WHERE notelabel='moreTdep'));\n",
        encoding="utf-8",
    )

    # Now use them (Pylance warning disappears)
    db = SanderHenryDatabase(sqlite_path=sqlite_path, sql_path=sql_path)
    conn = db._connect()

    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    assert "species" in tables
    assert "henry" in tables
    assert "henry_notes" in tables

    assert conn.execute("SELECT COUNT(*) FROM species").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM henry").fetchone()[0] == 1