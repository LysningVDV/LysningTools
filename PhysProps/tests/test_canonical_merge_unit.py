import pytest
import pandas as pd
import numpy as np

from tests.conftest import write_xlsx, read_xlsx


def _mock_builder_return(canonical_new: pd.DataFrame, audit: pd.DataFrame):
    """Factory producing a build_canonical_dataframe mock."""
    def _mock(df_wide, strict_schema=True):
        return canonical_new.copy(), audit.copy()
    return _mock


def test_merge_requires_inchi_key(tmp_path, monkeypatch):
    import physprops.io.excel_io as excel_io

    wide_path = tmp_path / "wide.xlsx"
    write_xlsx(pd.DataFrame({"x": [1]}), wide_path)

    # Builder returns a canonical df WITHOUT inchi_key
    canonical_new = pd.DataFrame({"test_field": ["x"]})
    audit = pd.DataFrame({"msg": ["audit"]})

    monkeypatch.setattr(excel_io, "build_canonical_dataframe", _mock_builder_return(canonical_new, audit))

    with pytest.raises(ValueError):
        excel_io.update_canonical_database(
            wide_excel_path=str(wide_path),
            canonical_db_path=str(tmp_path / "canonical.xlsx"),
            audit_excel_path=str(tmp_path / "audit.xlsx"),
            sheet_name=None,
            strict_schema=True,
        )


def test_blank_does_not_overwrite_existing(tmp_path, monkeypatch):
    import physprops.io.excel_io as excel_io

    # Existing canonical DB
    canonical_old = pd.DataFrame({
        "inchi_key": ["AAAA"],
        "test_field": [123],
    })
    canonical_path = tmp_path / "canonical_physprops.xlsx"
    write_xlsx(canonical_old, canonical_path)

    # Wide workbook (content irrelevant because builder is mocked)
    wide_path = tmp_path / "wide.xlsx"
    write_xlsx(pd.DataFrame({"x": [1]}), wide_path)

    # New canonical has blank for test_field
    canonical_new = pd.DataFrame({
        "inchi_key": ["AAAA"],
        "test_field": [""],
    })
    audit = pd.DataFrame({"note": ["run1"]})

    monkeypatch.setattr(excel_io, "build_canonical_dataframe", _mock_builder_return(canonical_new, audit))

    excel_io.update_canonical_database(
        wide_excel_path=str(wide_path),
        canonical_db_path=str(canonical_path),
        audit_excel_path=str(tmp_path / "canonical_physprops_audit.xlsx"),
        sheet_name=None,
        strict_schema=True,
    )

    merged = read_xlsx(canonical_path)
    assert merged.loc[0, "inchi_key"] == "AAAA"
    assert int(merged.loc[0, "test_field"]) == 123


def test_whitespace_blank_does_not_overwrite_existing(tmp_path, monkeypatch):
    import physprops.io.excel_io as excel_io

    canonical_old = pd.DataFrame({
        "inchi_key": ["AAAA"],
        "test_field": [123],
    })
    canonical_path = tmp_path / "canonical_physprops.xlsx"
    write_xlsx(canonical_old, canonical_path)

    wide_path = tmp_path / "wide.xlsx"
    write_xlsx(pd.DataFrame({"x": [1]}), wide_path)

    canonical_new = pd.DataFrame({
        "inchi_key": ["AAAA"],
        "test_field": ["   "],
    })
    audit = pd.DataFrame({"note": ["run1"]})

    monkeypatch.setattr(excel_io, "build_canonical_dataframe", _mock_builder_return(canonical_new, audit))

    excel_io.update_canonical_database(
        wide_excel_path=str(wide_path),
        canonical_db_path=str(canonical_path),
        audit_excel_path=str(tmp_path / "canonical_physprops_audit.xlsx"),
        sheet_name=None,
        strict_schema=True,
    )

    merged = read_xlsx(canonical_path)
    assert int(merged.loc[0, "test_field"]) == 123


def test_nonblank_overwrites_existing(tmp_path, monkeypatch):
    import physprops.io.excel_io as excel_io

    canonical_old = pd.DataFrame({
        "inchi_key": ["AAAA"],
        "test_field": [123],
    })
    canonical_path = tmp_path / "canonical_physprops.xlsx"
    write_xlsx(canonical_old, canonical_path)

    wide_path = tmp_path / "wide.xlsx"
    write_xlsx(pd.DataFrame({"x": [1]}), wide_path)

    canonical_new = pd.DataFrame({
        "inchi_key": ["AAAA"],
        "test_field": [456],
    })
    audit = pd.DataFrame({"note": ["run2"]})

    monkeypatch.setattr(excel_io, "build_canonical_dataframe", _mock_builder_return(canonical_new, audit))

    excel_io.update_canonical_database(
        wide_excel_path=str(wide_path),
        canonical_db_path=str(canonical_path),
        audit_excel_path=str(tmp_path / "canonical_physprops_audit.xlsx"),
        sheet_name=None,
        strict_schema=True,
    )

    merged = read_xlsx(canonical_path)
    assert int(merged.loc[0, "test_field"]) == 456


def test_new_inchikey_appended(tmp_path, monkeypatch):
    import physprops.io.excel_io as excel_io

    canonical_old = pd.DataFrame({
        "inchi_key": ["AAAA"],
        "test_field": [123],
    })
    canonical_path = tmp_path / "canonical_physprops.xlsx"
    write_xlsx(canonical_old, canonical_path)

    wide_path = tmp_path / "wide.xlsx"
    write_xlsx(pd.DataFrame({"x": [1]}), wide_path)

    canonical_new = pd.DataFrame({
        "inchi_key": ["AAAA", "BBBB"],
        "test_field": [np.nan, 999],
    })
    audit = pd.DataFrame({"note": ["run3"]})

    monkeypatch.setattr(excel_io, "build_canonical_dataframe", _mock_builder_return(canonical_new, audit))

    excel_io.update_canonical_database(
        wide_excel_path=str(wide_path),
        canonical_db_path=str(canonical_path),
        audit_excel_path=str(tmp_path / "canonical_physprops_audit.xlsx"),
        sheet_name=None,
        strict_schema=True,
    )

    merged = read_xlsx(canonical_path)
    assert set(merged["inchi_key"].astype(str)) == {"AAAA", "BBBB"}


def test_audit_overwritten_each_run(tmp_path, monkeypatch):
    import physprops.io.excel_io as excel_io

    canonical_path = tmp_path / "canonical_physprops.xlsx"
    write_xlsx(pd.DataFrame({"inchi_key": ["AAAA"], "test_field": [1]}), canonical_path)

    wide_path = tmp_path / "wide.xlsx"
    write_xlsx(pd.DataFrame({"x": [1]}), wide_path)

    audit_path = tmp_path / "canonical_physprops_audit.xlsx"

    # run 1
    canonical_new1 = pd.DataFrame({"inchi_key": ["AAAA"], "test_field": [1]})
    audit1 = pd.DataFrame({"note": ["first"]})
    monkeypatch.setattr(excel_io, "build_canonical_dataframe", _mock_builder_return(canonical_new1, audit1))
    excel_io.update_canonical_database(
        wide_excel_path=str(wide_path),
        canonical_db_path=str(canonical_path),
        audit_excel_path=str(audit_path),
        sheet_name=None,
        strict_schema=True,
    )
    got1 = read_xlsx(audit_path)
    assert got1.loc[0, "note"] == "first"

    # run 2 (overwrite)
    canonical_new2 = pd.DataFrame({"inchi_key": ["AAAA"], "test_field": [1]})
    audit2 = pd.DataFrame({"note": ["second"]})
    monkeypatch.setattr(excel_io, "build_canonical_dataframe", _mock_builder_return(canonical_new2, audit2))
    excel_io.update_canonical_database(
        wide_excel_path=str(wide_path),
        canonical_db_path=str(canonical_path),
        audit_excel_path=str(audit_path),
        sheet_name=None,
        strict_schema=True,
    )
    got2 = read_xlsx(audit_path)
    assert got2.loc[0, "note"] == "second"
