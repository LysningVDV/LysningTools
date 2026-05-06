import pytest
from rdkit import Chem

from chem_annotator.features.aldehydes import classify_aldehyde


def _mol(smiles: str) -> Chem.Mol:
    m = Chem.MolFromSmiles(smiles)
    assert m is not None, f"RDKit failed to parse SMILES: {smiles}"
    return m


# Keys we care about in this "A" core suite.
CORE_KEYS = (
    "AldehydeCount",
    "AldehydeCount_AlphaSubstituted",
    "AldehydeCount_BetaSubstituted",
    "AldehydeCount_NoAlphaBetaSub",
    "ArylAldehydeCount",
    "CyclicAliphaticAldehydeCount",
    "CyclicAldehyde_BetaSubCount_0",
    "CyclicAldehyde_BetaSubCount_1",
    "CyclicAldehyde_BetaSubCount_2",
    "CyclicAldehyde_BetaSubstitutedCount",
    "CyclicAldehyde_NonBetaSubstitutedCount",
    "AlphaBetaUnsaturatedAldehydeCount",
)


@pytest.mark.parametrize(
    "smiles, expected, audit_must_contain, audit_must_not_contain",
    [
        # -------------------------
        # Simple aliphatic aldehydes
        # -------------------------

        # Propanal: CH3-CH2-CHO
        # Alpha carbon is CH2 (not branched), beta carbon is CH3 (not branched) -> NoAlphaBetaSub.
        pytest.param(
            "CCC=O",
            {
                "AldehydeCount": 1,
                "AldehydeCount_NoAlphaBetaSub": 1,
                "AlphaBetaUnsaturatedAldehydeCount": 0,
            },
            ["acyclic", "noAlphaBetaSub"],
            [],
            id="propanal_no_alpha_beta_sub",
        ),

        # 2-methylpropanal (isobutyraldehyde): (CH3)2CH-CHO
        # Alpha carbon is branched (two carbon neighbors besides carbonyl C) -> AlphaSubstituted.
        pytest.param(
            "CC(C)C=O",
            {
                "AldehydeCount": 1,
                "AldehydeCount_AlphaSubstituted": 1,
                "AlphaBetaUnsaturatedAldehydeCount": 0,
            },
            ["acyclic", "alphaSub"],
            [],
            id="isobutyraldehyde_alpha_sub",
        ),

        # 3-methylbutanal: CH3-CH(CH3)-CH2-CHO
        # Alpha is CH2 (not branched), beta is CH with methyl branch -> BetaSubstituted.
        pytest.param(
            "CC(C)CC=O",
            {
                "AldehydeCount": 1,
                "AldehydeCount_BetaSubstituted": 1,
                "AlphaBetaUnsaturatedAldehydeCount": 0,
            },
            ["acyclic", "betaSub"],
            [],
            id="3_methylbutanal_beta_sub",
        ),

        # -------------------------
        # Alpha,beta-unsaturated (enal) aldehydes
        # -------------------------

        # Acrolein: CH2=CH-CHO
        # Alpha carbon participates in C=C -> AlphaBetaUnsaturated.
        # Side-chain substitution class remains NoAlphaBetaSub (no alpha or beta branching).
        pytest.param(
            "C=CC=O",
            {
                "AldehydeCount": 1,
                "AldehydeCount_NoAlphaBetaSub": 1,
                "AlphaBetaUnsaturatedAldehydeCount": 1,
            },
            ["acyclic", "ab-unsat"],
            [],
            id="acrolein_ab_unsat",
        ),

        # Crotonaldehyde: CH3-CH=CH-CHO
        # Still ab-unsaturated; no alpha branching and beta isn't branched by this heuristic.
        pytest.param(
            "CC=CC=O",
            {
                "AldehydeCount": 1,
                "AldehydeCount_NoAlphaBetaSub": 1,
                "AlphaBetaUnsaturatedAldehydeCount": 1,
            },
            ["acyclic", "ab-unsat"],
            [],
            id="crotonaldehyde_ab_unsat",
        ),

        # -------------------------
        # Aromatic (aryl) aldehydes
        # -------------------------

        # Benzaldehyde: Ph-CHO
        # Context: aryl aldehyde; also conjugated => AlphaBetaUnsaturated by your definition.
        # IMPORTANT overlap rule for this test suite:
        # - Aryl aldehydes should NOT contribute to "CyclicAldehyde_BetaSubCount_*" buckets,
        #   which are intended for cyclic ALIPHATIC aldehydes (separate context already exists).
        pytest.param(
            "O=Cc1ccccc1",
            {
                "AldehydeCount": 1,
                "ArylAldehydeCount": 1,
                "CyclicAliphaticAldehydeCount": 0,
                "AlphaBetaUnsaturatedAldehydeCount": 1,
                "CyclicAldehyde_BetaSubCount_0": 0,
                "CyclicAldehyde_BetaSubCount_1": 0,
                "CyclicAldehyde_BetaSubCount_2": 0,
            },
            ["aryl", "ab-unsat"],
            ["cyclicBetaSub="],
            id="benzaldehyde_aryl_not_cyclic_beta_bucket",
        ),

        # p-Tolualdehyde: methylbenzaldehyde (aryl aldehyde)
        pytest.param(
            "Cc1ccc(C=O)cc1",
            {
                "AldehydeCount": 1,
                "ArylAldehydeCount": 1,
                "CyclicAliphaticAldehydeCount": 0,
                "AlphaBetaUnsaturatedAldehydeCount": 1,
                "CyclicAldehyde_BetaSubCount_0": 0,
                "CyclicAldehyde_BetaSubCount_1": 0,
                "CyclicAldehyde_BetaSubCount_2": 0,
            },
            ["aryl", "ab-unsat"],
            ["cyclicBetaSub="],
            id="p_tolualdehyde_aryl_not_cyclic_beta_bucket",
        ),

        # -------------------------
        # Cyclic aliphatic aldehyde
        # -------------------------

        # Cyclohexanecarbaldehyde: cyclohexyl-CHO
        # Alpha carbon is in an aliphatic ring => CyclicAliphaticAldehydeCount.
        # Beta ring atoms adjacent to alpha are unsubstituted => cyclic beta sub count = 0.
        pytest.param(
            "O=CC1CCCCC1",
            {
                "AldehydeCount": 1,
                "CyclicAliphaticAldehydeCount": 1,
                "ArylAldehydeCount": 0,
                "AlphaBetaUnsaturatedAldehydeCount": 0,
                "CyclicAldehyde_BetaSubCount_0": 1,
                "CyclicAldehyde_BetaSubCount_1": 0,
                "CyclicAldehyde_BetaSubCount_2": 0,
                "CyclicAldehyde_NonBetaSubstitutedCount": 1,
                "CyclicAldehyde_BetaSubstitutedCount": 0,
            },
            ["cyclic-aliph", "cyclicBetaSub=0"],
            ["aryl"],
            id="cyclohexanecarbaldehyde_cyclic_beta0",
        ),

        # -------------------------
        # Multiple aldehydes in one molecule
        # -------------------------

        # Pentanedial (glutaraldehyde): OHC-(CH2)3-CHO
        # Two aldehyde centers. Both are simple aliphatic ends => NoAlphaBetaSub x2.
        pytest.param(
            "O=CCCCC=O",
            {
                "AldehydeCount": 2,
                "AldehydeCount_NoAlphaBetaSub": 2,
                "AlphaBetaUnsaturatedAldehydeCount": 0,
            },
            ["ald@"],
            [],
            id="glutaraldehyde_two_aldehydes",
        ),

        # -------------------------
        # Negative controls (should be excluded)
        # -------------------------

        # Formaldehyde has no alpha carbon (no carbon neighbor) => excluded by design.
        pytest.param(
            "C=O",
            {"AldehydeCount": 0},
            [],
            ["ald@"],
            id="formaldehyde_excluded_no_alpha_carbon",
        ),

        # Acetone is a ketone => excluded.
        pytest.param(
            "CC(=O)C",
            {"AldehydeCount": 0},
            [],
            ["ald@"],
            id="acetone_not_aldehyde",
        ),
    ],
)
def test_aldehydes_A_core_classification(smiles, expected, audit_must_contain, audit_must_not_contain):
    """
    Core aldehyde classification tests for classify_aldehyde().

    Overlap rules (explicit):
      - AldehydeCount is the number of aldehyde centers detected (carbonyl C with >=1 H and an alpha carbon).
      - ArylAldehydeCount and CyclicAliphaticAldehydeCount are context bins and should not double-count each other.
      - Side-chain substitution classes (AlphaSubstituted / BetaSubstituted / NoAlphaBetaSub) apply only to
        non-ring alpha carbons (acyclic side chains) and are mutually exclusive.
      - CyclicAldehyde_BetaSubCount_* buckets are intended here for cyclic ALIPHATIC aldehydes only
        (aryl aldehydes are handled by ArylAldehydeCount).
      - AlphaBetaUnsaturatedAldehydeCount counts enals and aryl-conjugated aldehydes.
    """
    m = _mol(smiles)
    counts, audit = classify_aldehyde(m)

    # Basic key presence sanity (prevents accidental key removals).
    for k in CORE_KEYS:
        assert k in counts, f"Missing expected key {k}"

    # Check expected subset.
    for k, v in expected.items():
        assert counts[k] == v, f"{smiles} key={k} got={counts[k]} expected={v}"

    # Internal consistency: cyclic rollups should match granular buckets.
    assert counts["CyclicAldehyde_BetaSubstitutedCount"] == (
        counts["CyclicAldehyde_BetaSubCount_1"] + counts["CyclicAldehyde_BetaSubCount_2"]
    )
    assert counts["CyclicAldehyde_NonBetaSubstitutedCount"] == counts["CyclicAldehyde_BetaSubCount_0"]

    # Audit string expectations (lightweight but catches classification regressions).
    for token in audit_must_contain:
        assert token in audit, f"Audit missing token {token!r} for {smiles}. Audit={audit!r}"
    for token in audit_must_not_contain:
        assert token not in audit, f"Audit unexpectedly contains {token!r} for {smiles}. Audit={audit!r}"

    # If AldehydeCount=0, audit should not contain any ald@ entries.
    if counts["AldehydeCount"] == 0:
        assert "ald@" not in audit