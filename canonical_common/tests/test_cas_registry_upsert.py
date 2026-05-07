import pandas as pd

from canonical_common.cas_registry import (
    upsert_registry,
    DEFAULT_DB2_COLUMNS,
)


def _df(rows):
    """Small helper to build a DataFrame from list[dict]."""
    return pd.DataFrame(rows)


def test_one_to_many_marks_ambiguous_and_keeps_both_mappings():
    """
    Conflict policy MVP:
    - allow one-to-many CAS→InChIKey
    - never overwrite silently
    - if CAS maps to >=2 joinable InChIKeys, mark joinable rows ambiguous and keep both rows
    """
    allowlist = list(DEFAULT_DB2_COLUMNS)

    existing = _df([
        {
            "cas_input": "50-00-0",
            "cas_number_normalized": "50-00-0",
            "cas_status": "valid",
            "inchi_key": "AAAA-BBBB-CCCC",
            "inchi": "",
            "smiles": "",
            "resolver_source": "sourceA",
            "resolver_confidence": 0.9,
            "resolution_timestamp_utc": "2026-01-01T00:00:00+00:00",
            "evidence": "old",
            "notes": "",
        }
    ])

    incoming = _df([
        {
            "cas_input": "50-00-0",
            "cas_number_normalized": "50-00-0",
            "cas_status": "valid",
            "inchi_key": "ZZZZ-YYYY-XXXX",
            "inchi": "",
            "smiles": "",
            "resolver_source": "sourceB",
            "resolver_confidence": 0.8,
            "resolution_timestamp_utc": "2026-01-02T00:00:00+00:00",
            "evidence": "new",
            "notes": "",
        }
    ])

    res = upsert_registry(existing, incoming, allowlist)

    # Both mappings must exist (one-to-many allowed)
    assert set(res.updated_registry["inchi_key"]) == {"AAAA-BBBB-CCCC", "ZZZZ-YYYY-XXXX"}

    # Both rows should be marked ambiguous (joinable rows only)
    sub = res.updated_registry[res.updated_registry["cas_number_normalized"] == "50-00-0"]
    assert set(sub["cas_status"]) == {"ambiguous"}

    # Audit should record the conflict event
    assert (res.audit["event"] == "cas_conflict_mark_ambiguous").any()


def test_same_key_is_non_destructive_fill_blanks_and_upgrade_confidence():
    """
    Same composite key (cas_number_normalized, inchi_key):
    - should fill blanks (inchi/smiles/etc.) from incoming
    - should NOT overwrite existing non-empty values
    - should upgrade confidence if incoming is higher
    - should refresh timestamp to later if newer
    - should append evidence/notes deterministically
    """
    allowlist = list(DEFAULT_DB2_COLUMNS)

    existing = _df([
        {
            "cas_input": "64-17-5",
            "cas_number_normalized": "64-17-5",
            "cas_status": "valid",
            "inchi_key": "ETOH-KEY-1234",
            "inchi": "",
            "smiles": "",
            "resolver_source": "A",
            "resolver_confidence": 0.5,
            "resolution_timestamp_utc": "2026-01-01T00:00:00+00:00",
            "evidence": "old",
            "notes": "",
        }
    ])

    incoming = _df([
        {
            "cas_input": "64-17-5",
            "cas_number_normalized": "64-17-5",
            "cas_status": "valid",
            "inchi_key": "ETOH-KEY-1234",
            "inchi": "InChI=1S/C2H6O/c1-2-3/h3H,2H2,1H3",
            "smiles": "CCO",
            "resolver_source": "B",
            "resolver_confidence": 0.9,
            "resolution_timestamp_utc": "2026-01-03T00:00:00+00:00",
            "evidence": "new",
            "notes": "note1",
        }
    ])

    res = upsert_registry(existing, incoming, allowlist)
    assert len(res.updated_registry) == 1
    row = res.updated_registry.iloc[0]

    # Filled blanks from incoming
    assert row["smiles"] == "CCO"
    assert str(row["inchi"]).startswith("InChI=")

    # Confidence upgraded, and source updated to the higher-confidence source
    assert float(row["resolver_confidence"]) == 0.9
    assert row["resolver_source"] == "B"

    # Timestamp refreshed to later (lexicographic ISO works here)
    assert row["resolution_timestamp_utc"] == "2026-01-03T00:00:00+00:00"

    # Evidence/notes appended (order doesn't matter, but both should be present)
    assert "old" in row["evidence"]
    assert "new" in row["evidence"]
    assert "note1" in row["notes"]

    # Audit should include an update event
    assert (res.audit["event"] == "update_existing_mapping").any()


def test_mixture_or_uvcb_rows_do_not_trigger_ambiguity_with_joinable_mappings():
    """
    Mixture/UVCB rows have empty inchi_key and should not be treated as joinable mappings.
    They should not trigger or be forced to ambiguous solely because joinable mappings exist.
    """
    allowlist = list(DEFAULT_DB2_COLUMNS)

    existing = _df([
        {
            "cas_input": "9999-99-9",
            "cas_number_normalized": "9999-99-9",
            "cas_status": "mixture",
            "inchi_key": "",
            "inchi": "",
            "smiles": "",
            "resolver_source": "manual",
            "resolver_confidence": pd.NA,
            "resolution_timestamp_utc": "2026-01-01T00:00:00+00:00",
            "evidence": "mixture declared",
            "notes": "",
        }
    ])

    incoming = _df([
        {
            "cas_input": "9999-99-9",
            "cas_number_normalized": "9999-99-9",
            "cas_status": "valid",
            "inchi_key": "KEY-ONE-111",
            "inchi": "",
            "smiles": "CCC",
            "resolver_source": "resolverX",
            "resolver_confidence": 0.7,
            "resolution_timestamp_utc": "2026-01-02T00:00:00+00:00",
            "evidence": "",
            "notes": "",
        }
    ])

    res = upsert_registry(existing, incoming, allowlist)

    # We should now have the mixture row AND the mapping row
    sub = res.updated_registry[res.updated_registry["cas_number_normalized"] == "9999-99-9"]
    assert len(sub) == 2

    # Mixture row stays mixture and does not become ambiguous
    mixture_row = sub[sub["inchi_key"] == ""].iloc[0]
    assert mixture_row["cas_status"] == "mixture"

    # The joinable mapping row is valid (only one joinable IK exists, so no ambiguity)
    map_row = sub[sub["inchi_key"] == "KEY-ONE-111"].iloc[0]
    assert map_row["cas_status"] in {"valid", "repaired", "unresolved"}  # depending on normalization rules


def test_rejected_rows_missing_normalized_cas_or_invalid_status_are_rejected():
    """
    Your cas_registry.py MVP rejects:
    - rows with missing cas_number_normalized
    - rows with cas_status=invalid
    """
    allowlist = list(DEFAULT_DB2_COLUMNS)

    existing = _df([])

    incoming = _df([
        {
            "cas_input": "raw",
            "cas_number_normalized": "",
            "cas_status": "valid",
            "inchi_key": "KEY-A",
            "resolver_source": "X",
            "resolver_confidence": 0.5,
            "resolution_timestamp_utc": "2026-01-01T00:00:00+00:00",
            "inchi": "",
            "smiles": "",
            "evidence": "",
            "notes": "",
        },
        {
            "cas_input": "bad",
            "cas_number_normalized": "12-34-5",
            "cas_status": "invalid",
            "inchi_key": "",
            "resolver_source": "X",
            "resolver_confidence": pd.NA,
            "resolution_timestamp_utc": "2026-01-01T00:00:00+00:00",
            "inchi": "",
            "smiles": "",
            "evidence": "checksum failed",
            "notes": "",
        },
        {
            "cas_input": "good",
            "cas_number_normalized": "64-17-5",
            "cas_status": "valid",
            "inchi_key": "ETOH-KEY-1234",
            "resolver_source": "X",
            "resolver_confidence": 0.5,
            "resolution_timestamp_utc": "2026-01-01T00:00:00+00:00",
            "inchi": "",
            "smiles": "",
            "evidence": "",
            "notes": "",
        },
    ])

    res = upsert_registry(existing, incoming, allowlist)

    # One accepted row
    assert len(res.updated_registry) == 1
    assert res.updated_registry.iloc[0]["cas_number_normalized"] == "64-17-5"

    # Two rejected rows, with reason column
    assert len(res.rejected) == 2
    assert "rejected_reason" in res.rejected.columns
    assert set(res.rejected["rejected_reason"].astype(str).tolist()) == {
        "missing cas_number_normalized",
        "cas_status=invalid",
    }


def test_deterministic_sort_order_by_cas_status_inchikey_timestamp():
    """
    The upsert sorts deterministically by:
      cas_number_normalized, cas_status, inchi_key, resolution_timestamp_utc
    This test checks the ordering is stable and not dependent on insertion order.
    """
    allowlist = list(DEFAULT_DB2_COLUMNS)

    existing = _df([
        {
            "cas_input": "x",
            "cas_number_normalized": "10-00-0",
            "cas_status": "valid",
            "inchi_key": "B-KEY",
            "inchi": "",
            "smiles": "",
            "resolver_source": "s",
            "resolver_confidence": 0.1,
            "resolution_timestamp_utc": "2026-01-02T00:00:00+00:00",
            "evidence": "",
            "notes": "",
        },
        {
            "cas_input": "x",
            "cas_number_normalized": "10-00-0",
            "cas_status": "valid",
            "inchi_key": "A-KEY",
            "inchi": "",
            "smiles": "",
            "resolver_source": "s",
            "resolver_confidence": 0.1,
            "resolution_timestamp_utc": "2026-01-01T00:00:00+00:00",
            "evidence": "",
            "notes": "",
        },
    ])

    incoming = _df([])

    res = upsert_registry(existing, incoming, allowlist)

    # Expect A-KEY row comes before B-KEY (since inchi_key sorted)
    sub = res.updated_registry[res.updated_registry["cas_number_normalized"] == "10-00-0"]
    assert sub.iloc[0]["inchi_key"] == "A-KEY"
    assert sub.iloc[1]["inchi_key"] == "B-KEY"