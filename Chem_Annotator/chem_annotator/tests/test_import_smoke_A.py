def test_import_smoke_package_and_schema():
    # Basic package import should succeed (catches import cycles / missing deps at import time)
    import chem_annotator  # noqa: F401

    # Canonical schema should import cleanly
    from chem_annotator import schema  # noqa: F401
    from chem_annotator.schema import FEATURE_DEFAULTS, FEATURE_KEYS  # noqa: F401

    # Aggregator import should succeed and expose the main entrypoint
    from chem_annotator.aggregator import features_for_smiles  # noqa: F401

    # Sanity: schema constants are non-empty
    assert isinstance(FEATURE_KEYS, tuple)
    assert len(FEATURE_KEYS) > 0
    assert isinstance(FEATURE_DEFAULTS, dict)
    assert len(FEATURE_DEFAULTS) == len(FEATURE_KEYS)