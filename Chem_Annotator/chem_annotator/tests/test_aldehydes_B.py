import pytest
from rdkit import Chem

from chem_annotator.features.aldehydes import classify_aldehyde


def _mol(smiles: str) -> Chem.Mol:
    m = Chem.MolFromSmiles(smiles)
    assert m is not None, f"RDKit failed to parse SMILES: {smiles}"
    return m


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
    "smiles, expected_subset, must_contain, must_not_contain",
    [
        # -------------------------
        # Heteroatom substitution edges (acyclic)
        # -------------------------

        # 3-hydroxy propanal HO-CH2-CHO:
        # Alpha carbon exists (CH2), not branched, no beta carbon -> NoAlphaBetaSub.
        pytest.param(
            "OCCC=O",
            {"AldehydeCount": 1, "AldehydeCount_NoAlphaBetaSub": 1, "AlphaBetaUnsaturatedAldehydeCount": 0},
            ["acyclic", "noAlphaBetaSub"],
            [],
            id="3_hydroxypropanal_no_alpha_beta_sub_carbon_only_model",
        ),


        # Chloroacetaldehyde Cl-CH2-CHO:
        # Still a simple aldehyde under this model (Cl does not create alpha branching by your definition).
        pytest.param(
            "ClCC=O",
            {"AldehydeCount": 1, "AldehydeCount_NoAlphaBetaSub": 1, "AlphaBetaUnsaturatedAldehydeCount": 0},
            ["acyclic", "noAlphaBetaSub"],
            [],
            id="chloroacetaldehyde_no_alpha_beta_sub",
        ),

        # 3,3-dimethylbutanal: CC(C)(C)CC=O Here, relative to the aldehyde: α = CH2 β = carbon bearing two methyl substituents → true carbon branching ⇒ BetaSubstituted = 1
        # Alpha carbon is CH2; beta carbon bears heteroatom substituent (OH) -> BetaSubstituted.
        pytest.param(
            "CC(C)(C)CC=O",
            {"AldehydeCount": 1, "AldehydeCount_BetaSubstituted": 1, "AlphaBetaUnsaturatedAldehydeCount": 0},
            ["acyclic", "betaSub"],
            [],
            id="3_3_dimethylbutanal_beta_sub_carbon_branching",
        ),


        # 2-hydroxypropanal CH3-CH(OH)-CHO:
        # Alpha carbon has two neighbors besides carbonyl carbon (CH3 and O) -> AlphaSubstituted per your rule.
        pytest.param(
            "CC(O)C=O",
            {"AldehydeCount": 1, "AldehydeCount_NoAlphaBetaSub": 1, "AlphaBetaUnsaturatedAldehydeCount": 0},
            ["acyclic", "noAlphaBetaSub"],
            [],
            id="2_hydroxypropanal_alpha_sub",
        ),

        # -------------------------
        # Heteroaromatic aryl aldehyde (regression guard)
        # -------------------------

        # Furan-2-carbaldehyde:
        # Alpha atom is aromatic -> ArylAldehydeCount and ab-unsat (aromatic conjugation).
        # Must NOT populate cyclic-aliphatic beta-sub buckets.
        pytest.param(
            "O=Cc1ccco1",
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
            id="furfural_aryl_no_cyclic_beta_buckets",
        ),

        # -------------------------
        # Multi-aldehyde edge case (alpha carbon is itself carbonyl carbon)
        # -------------------------

        # Glyoxal OHC-CHO:
        # Two aldehyde centers; each has an alpha carbon (the other carbonyl carbon) -> AldehydeCount=2.
        # No alpha/beta branching -> NoAlphaBetaSub x2.
        pytest.param(
            "O=CC=O",
            {"AldehydeCount": 2, "AldehydeCount_NoAlphaBetaSub": 2, "AlphaBetaUnsaturatedAldehydeCount": 0},
            ["ald@"],
            [],
            id="glyoxal_two_aldehydes",
        ),

        # -------------------------
        # Negative controls: acid derivatives / ketones / formates
        # -------------------------

        # Acetyl chloride is not an aldehyde (no aldehydic H on carbonyl carbon).
        pytest.param(
            "CC(=O)Cl",
            {"AldehydeCount": 0},
            [],
            ["ald@"],
            id="acyl_chloride_not_aldehyde",
        ),

        # Acetic acid is not an aldehyde.
        pytest.param(
            "CC(=O)O",
            {"AldehydeCount": 0},
            [],
            ["ald@"],
            id="carboxylic_acid_not_aldehyde",
        ),

        # Methyl formate is an ester; carbonyl carbon has H but no alpha carbon neighbor -> excluded by design.
        pytest.param(
            "COC=O",
            {"AldehydeCount": 0},
            [],
            ["ald@"],
            id="methyl_formate_excluded_no_alpha_carbon",
        ),

        # Ketone negative control (no carbonyl H).
        pytest.param(
            "CCC(=O)C",
            {"AldehydeCount": 0},
            [],
            ["ald@"],
            id="ketone_not_aldehyde",
        ),
    ],
)
def test_aldehydes_B_edge_cases(smiles, expected_subset, must_contain, must_not_contain):
    """
    Edge / exclusion / negative-control tests for classify_aldehyde().

    Overlap rules (explicit):
      - Aldehyde center requires: carbonyl C (=O), >=1 H on that carbon (aldehydic), and an alpha carbon neighbor.
      - Aryl aldehydes are those with aromatic alpha; cyclic-aliphatic aldehydes are non-aromatic ring alpha.
      - Cyclic beta-sub buckets should only be used for cyclic aliphatic aldehydes (not aryl).
      - Side-chain substitution classes apply only when alpha is NOT in a ring (acyclic alpha).
    """
    m = _mol(smiles)
    counts, audit = classify_aldehyde(m)

    # Key presence
    for k in CORE_KEYS:
        assert k in counts, f"Missing expected key {k}"

    # Expected subset checks
    for k, v in expected_subset.items():
        assert counts[k] == v, f"{smiles} key={k} got={counts[k]} expected={v}"

    # Internal consistency rollups
    assert counts["CyclicAldehyde_BetaSubstitutedCount"] == (
        counts["CyclicAldehyde_BetaSubCount_1"] + counts["CyclicAldehyde_BetaSubCount_2"]
    )
    assert counts["CyclicAldehyde_NonBetaSubstitutedCount"] == counts["CyclicAldehyde_BetaSubCount_0"]

    for token in must_contain:
        assert token in audit, f"Audit missing {token!r} for {smiles}. Audit={audit!r}"
    for token in must_not_contain:
        assert token not in audit, f"Audit unexpectedly contains {token!r} for {smiles}. Audit={audit!r}"

    if counts["AldehydeCount"] == 0:
        assert "ald@" not in audit