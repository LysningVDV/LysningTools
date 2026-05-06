import json
import pathlib

DATA = pathlib.Path(__file__).parent / "regression_cases.json"


def test_regression_dataset(run):
    cases = json.loads(DATA.read_text(encoding="utf-8"))
    assert isinstance(cases, list) and cases, "Regression dataset must be a non-empty list of cases"

    # Guardrails: ensure dataset integrity (stable harness)
    names = []
    for i, case in enumerate(cases):
        assert isinstance(case, dict), f"Case #{i} must be a dict"
        assert "smiles" in case, f"Case #{i} missing required field 'smiles'"
        assert "expected" in case and isinstance(case["expected"], dict), f"Case #{i} missing dict field 'expected'"
        label = case.get("name", case["smiles"])
        names.append(label)

    assert len(set(names)) == len(names), f"Regression case names must be unique. Duplicates found: {names}"

    # Canonical defaults for invalid-SMILES rule enforcement (schema-stable)
    from chem_annotator.schema import FEATURE_DEFAULTS

    for case in cases:
        smi = case["smiles"]
        label = case.get("name", smi)
        result = run(smi)

        # If the case expects invalid, enforce the full robustness rule here too.
        if case["expected"].get("Valid") == 0:
            schema_keys = set(FEATURE_DEFAULTS.keys())
            result_keys = set(result.keys())
            assert result_keys == schema_keys, (
                f"[{label}] {smi}: invalid SMILES must return full schema. "
                f"Missing={schema_keys - result_keys} "
                f"Extra={result_keys - schema_keys}"
            )
            for k, default_v in FEATURE_DEFAULTS.items():
                assert result[k] == default_v, (
                    f"[{label}] {smi}: invalid SMILES expected default {k}={default_v!r}, got {result[k]!r}"
                )

        # Standard regression assertions (subset-based, stable across schema growth)
        for k, v in case["expected"].items():
            assert k in result, f"[{label}] {smi}: missing key '{k}' in result"
            assert result[k] == v, f"[{label}] {smi}: expected {k}={v!r}, got {result[k]!r}"