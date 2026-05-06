import pytest
from rdkit import Chem

from chem_annotator.features.aldehydes import classify_aldehyde


def _mol(smiles: str) -> Chem.Mol:
    m = Chem.MolFromSmiles(smiles)
    assert m is not None, f"RDKit failed to parse SMILES: {smiles}"
    return m


def _count_occurrences(haystack: str, needle: str) -> int:
    return haystack.count(needle)


@pytest.mark.parametrize(
    "smiles, expected_subset, audit_ald_centers",
    [
        # ------------------------------------------------------------
        # 1) Aromatic dialdehyde: two aryl aldehydes, both conjugated
        # ------------------------------------------------------------
        # Terephthaldehyde: OHC–Ph–CHO (para)
        # Two aldehydes. Both alpha atoms are aromatic => ArylAldehydeCount=2.
        # Both are "ab-unsat" by your definition (aromatic alpha).
        # Must not populate cyclic-aliphatic beta buckets.
        pytest.param(
            "O=CC1=CC=C(C=C1)C=O",
            {
                "AldehydeCount": 2,
                "ArylAldehydeCount": 2,
                "CyclicAliphaticAldehydeCount": 0,
                "AlphaBetaUnsaturatedAldehydeCount": 2,
                "CyclicAldehyde_BetaSubCount_0": 0,
                "CyclicAldehyde_BetaSubCount_1": 0,
                "CyclicAldehyde_BetaSubCount_2": 0,
            },
            2,
            id="terephthaldehyde_two_aryl_aldehydes",
        ),

        # ------------------------------------------------------------
        # 2) Mixed: one enal aldehyde + one saturated aldehyde
        # ------------------------------------------------------------
        # OHC–CH=CH–CH2–CHO
        # Two aldehyde centers.
        # Left aldehyde is alpha,beta-unsaturated (alpha has C=C) => ab-unsat +1.
        # Right aldehyde is saturated => no ab-unsat.
        # Both are acyclic side-chains with no branching => NoAlphaBetaSub=2.
        pytest.param(
            "O=CC=CCC=O",
            {
                "AldehydeCount": 2,
                "AlphaBetaUnsaturatedAldehydeCount": 1,
                "AldehydeCount_NoAlphaBetaSub": 2,
                "ArylAldehydeCount": 0,
                "CyclicAliphaticAldehydeCount": 0,
            },
            2,
            id="enal_plus_saturated_dialdehyde",
        ),

        # ------------------------------------------------------------
        # 3) Cinnamaldehyde: enal conjugated to phenyl, but alpha is vinylic not aromatic
        # ------------------------------------------------------------
        # Ph–CH=CH–CHO
        # One aldehyde. Alpha carbon is vinylic (not aromatic, not in ring).
        # ab-unsat should be True due to alpha C=C.
        # Not an aryl aldehyde in your definition (alpha isn't aromatic).
        pytest.param(
            "O=CC=CC1=CC=CC=C1",
            {
                "AldehydeCount": 1,
                "AlphaBetaUnsaturatedAldehydeCount": 1,
                "ArylAldehydeCount": 0,
                "CyclicAliphaticAldehydeCount": 0,
                "AldehydeCount_NoAlphaBetaSub": 1,
            },
            1,
            id="cinnamaldehyde_enal_not_aryl_by_alpha_definition",
        ),

        # ------------------------------------------------------------
        # 4) Cyclic aliphatic + alpha,beta unsaturation inside ring
        # ------------------------------------------------------------
        # Cyclohex-1-enecarbaldehyde (double bond adjacent to alpha ring carbon)
        # Alpha is in a non-aromatic ring => CyclicAliphaticAldehydeCount=1.
        # Alpha has a C=C bond => ab-unsat True.
        # Cyclic beta bucket should be used (not aryl).
        pytest.param(
            "O=CC1=CCCCC1",
            {
                "AldehydeCount": 1,
                "CyclicAliphaticAldehydeCount": 1,
                "AlphaBetaUnsaturatedAldehydeCount": 1,
                "ArylAldehydeCount": 0,
                # At least one cyclic bucket must increment; for this unsubstituted ring it should be 0-sub.
                "CyclicAldehyde_BetaSubCount_0": 1,
            },
            1,
            id="cyclohexenecarbaldehyde_cyclic_and_ab_unsat",
        ),

        # ------------------------------------------------------------
        # 5) Aldehyde + ketone in same molecule: ensure aldehyde detection unaffected
        # ------------------------------------------------------------
        # 4-oxobutanal: OHC-CH2-CH2-CO-CH3 (SMILES: CCC(=O)CC=O)
        # One aldehyde center only; ketone should not create extra aldehyde.
        pytest.param(
            "CCC(=O)CC=O",
            {
                "AldehydeCount": 1,
                "AldehydeCount_NoAlphaBetaSub": 1,
                "AlphaBetaUnsaturatedAldehydeCount": 0,
            },
            1,
            id="aldehyde_plus_ketone_only_one_aldehyde",
        ),

        # ------------------------------------------------------------
        # 6) Cyclic aliphatic ring substitution affecting cyclic beta bucket
        # ------------------------------------------------------------
        # 2-methylcyclohexanecarbaldehyde:
        # ring carbon adjacent to alpha has a methyl substituent -> expect cyclic beta-sub count >=1.
        # NOTE: depends on your definition: beta ring atoms are neighbors of alpha that are in ring.
        # If one of those beta atoms has an extra substituent (degree > 2), BetaSubCount_1 increments.
        pytest.param(
            "O=CC1C(C)CCCC1",
            {
                "AldehydeCount": 1,
                "CyclicAliphaticAldehydeCount": 1,
                "ArylAldehydeCount": 0,
                # should not be counted as 0-substituted
                "CyclicAldehyde_BetaSubCount_0": 0,
                "CyclicAldehyde_BetaSubstitutedCount": 1,
            },
            1,
            id="methylcyclohexanecarbaldehyde_cyclic_beta_sub",
        ),

        # ------------------------------------------------------------
        # 7) Heteroaromatic aryl aldehyde (regression): should remain aryl, not cyclic-aliphatic buckets
        # ------------------------------------------------------------
        # Furfural: furan-2-carbaldehyde
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
            1,
            id="furfural_regression_aryl_not_cyclic_beta",
        ),

        # ------------------------------------------------------------
        # 8) Multi-center + mixed substitution classes (acyclic branching)
        # ------------------------------------------------------------
        # 2-methyl-3-oxopropanal is tricky; instead use a clean dialdehyde with alpha substitution on one end:
        # (CH3)2CH-CHO  plus a second aldehyde tail: (CH3)2CH-CH2-CH2-CHO
        # SMILES: CC(C)CCC=O is one aldehyde; to create two centers, use: O=CCC(C)(C)C=O
        # This has two aldehydes: one end is alpha-substituted (tert-like), the other is simple.
        pytest.param(
            "O=CC(C)(C)CCC=O",
            {
            "AldehydeCount": 2,
            "AldehydeCount_AlphaSubstituted": 1,
            "AldehydeCount_NoAlphaBetaSub": 1,
            },
            2,
            id="dialdehyde_one_alpha_sub_one_simple",
    ),

    ],
)
def test_aldehydes_C_complex_overlaps(smiles, expected_subset, audit_ald_centers):
    """
    Complex/overlap/regression tests for classify_aldehyde().

    Key overlap rules enforced:
      - Aryl aldehydes (alpha aromatic) should NOT populate CyclicAldehyde_BetaSubCount_* buckets.
      - Cyclic-aliphatic aldehydes (alpha in non-aromatic ring) should populate cyclic beta buckets.
      - AlphaBetaUnsaturatedAldehydeCount can overlap with BOTH aryl aldehydes and cyclic aliphatic aldehydes
        (by your definitions).
      - Multiple aldehyde centers: AldehydeCount should equal the number of 'ald@' tags in audit.
    """
    m = _mol(smiles)
    counts, audit = classify_aldehyde(m)

    for k, v in expected_subset.items():
        assert counts.get(k) == v, f"{smiles} key={k} got={counts.get(k)} expected={v}"

    # Rollup consistency
    assert counts["CyclicAldehyde_BetaSubstitutedCount"] == (
        counts["CyclicAldehyde_BetaSubCount_1"] + counts["CyclicAldehyde_BetaSubCount_2"]
    )
    assert counts["CyclicAldehyde_NonBetaSubstitutedCount"] == counts["CyclicAldehyde_BetaSubCount_0"]

    # Audit sanity: number of aldehyde-center tags should match expected.
    assert _count_occurrences(audit, "ald@") == audit_ald_centers, f"{smiles} audit={audit!r}"