from chem_annotator.aggregator import features_for_smiles
from chem_annotator.schema import FEATURE_DEFAULTS

# "Recently added / recently expanded" keys we want to guard at integration level.
# This list is intentionally small and spans multiple families to avoid singling out one module.
#
# Design intent:
# - If schema changes, this is the first file to update (alongside aggregator/schema defaults).
# - Keys here should be stable, high-level, and easy to sanity-check on one or two molecules.
RECENT_KEYS = [
    # --- Ethers (expanded earlier: total/acyclic/cyclic/epoxide) ---
    "EtherCount_Total",
    "EtherCount_Acyclic",
    "EtherCount_Cyclic",
    "EpoxideCount",
    # --- Halogens (recent expansion: atoms, subtype splits, etc.) ---
    "HalogenAtomCount_Total",
    "HalogenAtomCount_Cl",
    "HalogenatedCarbonCount_Cl",
    "HalogenatedArylCarbonCount_Cl",
    "HalogenatedPhenolCount_Cl",
    # --- Macrocyclic (macro musks family) ---
    "MacroMusks_Total",
    "MacroMusks_Ketones",
    "MacroMusks_Lactones",
    # --- Unsaturation (strict C–C unsaturation used for IsFullySaturated) ---
    "NumUnsaturatedBonds",
    # --- Heterocycles
    "IndoleCount",
    "FuranCount",
    "ThiopheneCount",
]


def test_integration_schema_invalid_returns_full_zero_schema():
    """
    Integration guardrail:
    - Invalid SMILES must return ALL expected keys with numeric fields = 0, string fields = "" and Valid=0.
    - We verify this against the canonical schema defaults (single source of truth).
    """
    valid = features_for_smiles("Oc1ccc(Cl)cc1")  # stable parse; gives a concrete schema instance
    invalid = features_for_smiles("NOT_A_SMILES")

    assert valid.get("Valid") == 1
    assert invalid.get("Valid") == 0

    # 1) Schema completeness: both valid and invalid must match the canonical schema
    schema_keys = set(FEATURE_DEFAULTS.keys())

    assert set(valid.keys()) == schema_keys, (
        "Valid SMILES must return the full canonical schema. "
        f"Missing={schema_keys - set(valid.keys())} "
        f"Extra={set(valid.keys()) - schema_keys}"
    )

    assert set(invalid.keys()) == schema_keys, (
        "Invalid SMILES must return the full canonical schema. "
        f"Missing={schema_keys - set(invalid.keys())} "
        f"Extra={set(invalid.keys()) - schema_keys}"
    )

    # 2) All fields must be defaulted appropriately on invalid (0 for numeric, "" for string)
    for k, default_v in FEATURE_DEFAULTS.items():
        assert k in invalid, f"Expected key missing in invalid schema: {k}"
        assert invalid[k] == default_v, f"Invalid SMILES: expected {k}={default_v!r}, got {invalid[k]!r}"

    # 3) Representative numeric fields should be zero on invalid (spot-check)
    numeric_keys = [
        "TotalAlcoholCount",
        "AldehydeCount",
        "EtherCount_Total",
        "NitroGroupCount",
        "NumUnsaturatedBonds",
        "HalogenatedCarbonCount",
        "HalogenAtomCount_Total",
        "MacroMusks_Total",
        "HighImpactTier1Count",
        "HighImpactTier2Count",
    ]
    for k in numeric_keys:
        assert k in invalid, f"Expected key missing in invalid schema: {k}"
        assert invalid[k] == 0, f"Invalid SMILES: expected {k}=0, got {invalid[k]!r}"

    # 4) Representative string fields should be empty on invalid (spot-check)
    string_keys = ["AlcoholAudit", "AldehydeAudit", "HighImpactSummary"]
    for k in string_keys:
        assert k in invalid, f"Expected key missing in invalid schema: {k}"
        assert invalid[k] == "", f"Invalid SMILES: expected {k}='', got {invalid[k]!r}"


def test_integration_recent_keys_exist_in_valid_and_invalid():
    """
    Integration guardrail for recent schema expansions:
    - All keys in RECENT_KEYS must exist in BOTH valid and invalid outputs.
    - On invalid SMILES, these keys should be numeric zeros.
    """
    valid = features_for_smiles("Oc1ccc(Cl)cc1")
    invalid = features_for_smiles("NOT_A_SMILES")

    for k in RECENT_KEYS:
        assert k in FEATURE_DEFAULTS, f"RECENT_KEYS missing from canonical schema: {k}"
        assert k in valid, f"RECENT_KEYS missing from valid output: {k}"
        assert k in invalid, f"RECENT_KEYS missing from invalid output: {k}"
        assert invalid[k] == 0, f"Invalid SMILES: expected {k}=0, got {invalid[k]!r}"


def test_integration_recent_keys_sanity_on_simple_molecules():
    """
    Light sanity checks on a couple of simple molecules to ensure RECENT_KEYS aren't just present,
    but also behave plausibly without over-constraining chemistry.
    """
    # p-chlorophenol: should have at least one Cl atom and at least one halogenated aryl carbon site
    feats = features_for_smiles("Oc1ccc(Cl)cc1")
    assert feats["Valid"] == 1
    assert feats["HalogenAtomCount_Cl"] == 1
    assert feats["HalogenAtomCount_Total"] >= 1
    assert feats["HalogenatedCarbonCount_Cl"] >= 1
    assert feats["HalogenatedArylCarbonCount_Cl"] >= 1

    # cyclododecanone: macrocyclic ketone indicator should trigger macro total and ketones
    macro = features_for_smiles("O=C1CCCCCCCCCCC1")
    assert macro["Valid"] == 1
    assert macro["MacroMusks_Total"] >= 1
    assert macro["MacroMusks_Ketones"] >= 1
    # Lactones should remain zero here
    assert macro["MacroMusks_Lactones"] == 0