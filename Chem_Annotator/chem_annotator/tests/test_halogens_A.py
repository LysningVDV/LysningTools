import pytest
from rdkit import Chem

from chem_annotator.features.halogens import (
    count_halogen_atoms_total,
    count_halogen_atoms_by_halogen,
    count_halogenated_carbons,
    count_halogenated_carbons_by_halogen,
    count_halogenated_carbons_by_halogen_split_aromatic,
    count_halogenated_phenols,
    count_halogenated_phenols_by_halogen,
)


def _mol(smiles: str) -> Chem.Mol:
    m = Chem.MolFromSmiles(smiles)
    assert m is not None, f"RDKit failed to parse SMILES: {smiles}"
    return m


def _assert_subset(got: dict, expected_subset: dict, rationale: str):
    """Assert only the keys in expected_subset, to keep tests robust to extra keys."""
    for k, v in expected_subset.items():
        assert k in got, f"Missing key {k}. " + rationale
        assert got[k] == v, f"{k}: got {got[k]} expected {v}. " + rationale


# Overlap rules (explicit, chemistry-first):
# - Halogen atom counts are atom-based: CF3 has 3 F atoms.
# - Halogenated carbon counts are carbon-site based: a carbon counts once if bonded to ≥1 halogen,
#   regardless of how many halogens (e.g., CCl4 has 1 halogenated carbon).
# - Per-halogen carbon-site markers are NOT mutually exclusive: a carbon bonded to both F and Cl
#   increments both HalogenatedCarbonCount_F and _Cl (marker-style).
# - Halophenol counts are OH-site based: multiple phenolic OH on the same halogenated ring count multiple times.
# - Halophenol is ring-local: only halogens on the SAME aromatic ring as the phenolic attachment count.
# - Aromatic vs aliphatic split is based on whether the carbon site is aromatic (aryl) or not (alkyl).


@pytest.mark.parametrize(
    "smiles, exp_atoms_total, exp_atoms_by, exp_carb_total, exp_carb_by, exp_carb_split, exp_ph_total, exp_ph_by, rationale",
    [
        # 1) p-chlorophenol: halophenol (class marker), aryl C–Cl site
        pytest.param(
            "Oc1ccc(Cl)cc1",
            1,
            {"HalogenAtomCount_Cl": 1, "HalogenAtomCount_F": 0, "HalogenAtomCount_Br": 0, "HalogenAtomCount_I": 0},
            1,
            {"HalogenatedCarbonCount_Cl": 1},
            {"HalogenatedArylCarbonCount_Cl": 1, "HalogenatedAlkylCarbonCount_Cl": 0},
            1,
            {"HalogenatedPhenolCount_Cl": 1},
            "p-chlorophenol: 1 Cl atom; ipso aromatic carbon bonded to Cl => 1 aryl carbon site; "
            "phenolic OH on a ring bearing Cl => halophenol OH-site count 1.",
            id="p_chlorophenol",
        ),

        # 2) p-fluorophenol: include F as halogen; same logic as chlorophenol
        pytest.param(
            "Oc1ccc(F)cc1",
            1,
            {"HalogenAtomCount_F": 1, "HalogenAtomCount_Cl": 0, "HalogenAtomCount_Br": 0, "HalogenAtomCount_I": 0},
            1,
            {"HalogenatedCarbonCount_F": 1},
            {"HalogenatedArylCarbonCount_F": 1, "HalogenatedAlkylCarbonCount_F": 0},
            1,
            {"HalogenatedPhenolCount_F": 1},
            "p-fluorophenol: 1 F atom; aryl C–F ipso carbon site; phenolic OH on F-bearing ring => halophenol 1.",
            id="p_fluorophenol",
        ),

        # 3) chlorocatechol: two phenolic OH on same halogenated ring => OH-site count 2
        pytest.param(
            "Oc1cc(Cl)ccc1O",
            1,
            {"HalogenAtomCount_Cl": 1, "HalogenAtomCount_F": 0, "HalogenAtomCount_Br": 0, "HalogenAtomCount_I": 0},
            1,
            {"HalogenatedCarbonCount_Cl": 1},
            {"HalogenatedArylCarbonCount_Cl": 1},
            2,
            {"HalogenatedPhenolCount_Cl": 2},
            "chlorocatechol: 1 Cl atom; only one ring carbon bonded to Cl => 1 halogenated carbon site; "
            "two phenolic OH sites on the Cl-bearing ring => halophenol count 2 (OH-site based).",
            id="chlorocatechol_two_OH_one_Cl",
        ),

        # 4) mixed-halogen phenol: one OH site, ring has both Cl and Br => phenol markers both increment
        pytest.param(
            "Oc1ccc(Br)cc1Cl",
            2,
            {"HalogenAtomCount_Cl": 1, "HalogenAtomCount_Br": 1, "HalogenAtomCount_F": 0, "HalogenAtomCount_I": 0},
            2,
            {"HalogenatedCarbonCount_Cl": 1, "HalogenatedCarbonCount_Br": 1},
            {"HalogenatedArylCarbonCount_Cl": 1, "HalogenatedArylCarbonCount_Br": 1},
            1,
            {"HalogenatedPhenolCount_Cl": 1, "HalogenatedPhenolCount_Br": 1},
            "Mixed halophenol: ring contains Cl and Br; single OH site increments both phenol markers (marker-style). "
            "Two distinct aryl carbon sites bonded to halogens => carbon total 2.",
            id="mixed_halophenol_Cl_Br",
        ),

        # 5) aromatic dihalide without phenol: validates aryl carbon-site counting
        pytest.param(
            "c1ccc(Br)cc1Cl",
            2,
            {"HalogenAtomCount_Cl": 1, "HalogenAtomCount_Br": 1, "HalogenAtomCount_F": 0, "HalogenAtomCount_I": 0},
            2,
            {"HalogenatedCarbonCount_Cl": 1, "HalogenatedCarbonCount_Br": 1},
            {"HalogenatedArylCarbonCount_Cl": 1, "HalogenatedArylCarbonCount_Br": 1},
            0,
            {"HalogenatedPhenolCount_Cl": 0, "HalogenatedPhenolCount_Br": 0, "HalogenatedPhenolCount_F": 0, "HalogenatedPhenolCount_I": 0},
            "Dihalobenzene: two halogen atoms; two aryl carbon sites bonded to halogens; no phenolic OH => no halophenol.",
            id="dihalobenzene_Cl_Br_no_phenol",
        ),

        # 6) benzyl chloride: halogenated carbon is aliphatic (sp3), not aromatic
        pytest.param(
            "c1ccccc1CCl",
            1,
            {"HalogenAtomCount_Cl": 1, "HalogenAtomCount_F": 0, "HalogenAtomCount_Br": 0, "HalogenAtomCount_I": 0},
            1,
            {"HalogenatedCarbonCount_Cl": 1},
            {"HalogenatedAlkylCarbonCount_Cl": 1, "HalogenatedArylCarbonCount_Cl": 0},
            0,
            {"HalogenatedPhenolCount_Cl": 0},
            "Benzyl chloride: carbon site is benzylic (non-aromatic) => alkyl split increments; no phenol.",
            id="benzyl_chloride_alkyl_site",
        ),

        # 7) 1,2-dichloroethane: two carbon sites, both alkyl
        pytest.param(
            "ClCCCl",
            2,
            {"HalogenAtomCount_Cl": 2, "HalogenAtomCount_F": 0, "HalogenAtomCount_Br": 0, "HalogenAtomCount_I": 0},
            2,
            {"HalogenatedCarbonCount_Cl": 2},
            {"HalogenatedAlkylCarbonCount_Cl": 2, "HalogenatedArylCarbonCount_Cl": 0},
            0,
            {"HalogenatedPhenolCount_Cl": 0},
            "1,2-dichloroethane: two Cl atoms; each carbon bonded to Cl => 2 halogenated carbon sites; alkyl split.",
            id="dichloroethane_two_sites",
        ),

        # 8) carbon tetrachloride: one carbon site despite four Cl atoms
        pytest.param(
            "C(Cl)(Cl)(Cl)Cl",
            4,
            {"HalogenAtomCount_Cl": 4, "HalogenAtomCount_F": 0, "HalogenAtomCount_Br": 0, "HalogenAtomCount_I": 0},
            1,
            {"HalogenatedCarbonCount_Cl": 1},
            {"HalogenatedAlkylCarbonCount_Cl": 1},
            0,
            {"HalogenatedPhenolCount_Cl": 0},
            "CCl4: 4 Cl atoms but only one carbon atom; carbon-site counting => 1 halogenated carbon site.",
            id="carbon_tetrachloride_atom_vs_site",
        ),

        # 9) CF3-ethyl: 3 F atoms but 1 carbon site bonded to F
        pytest.param(
            "CC(F)(F)F",
            3,
            {"HalogenAtomCount_F": 3, "HalogenAtomCount_Cl": 0, "HalogenAtomCount_Br": 0, "HalogenAtomCount_I": 0},
            1,
            {"HalogenatedCarbonCount_F": 1},
            {"HalogenatedAlkylCarbonCount_F": 1},
            0,
            {"HalogenatedPhenolCount_F": 0},
            "Trifluoroethyl: three F atoms; the CF3 carbon is one carbon site bonded to F => carbon-site F count 1.",
            id="trifluoroethyl_atom_vs_site",
        ),

        # 10) chlorodifluoromethane: one carbon site with both F and Cl => multi-label markers
        pytest.param(
            "FC(F)Cl",
            3,
            {"HalogenAtomCount_F": 2, "HalogenAtomCount_Cl": 1, "HalogenAtomCount_Br": 0, "HalogenAtomCount_I": 0},
            1,
            {"HalogenatedCarbonCount_F": 1, "HalogenatedCarbonCount_Cl": 1},
            {"HalogenatedAlkylCarbonCount_F": 1, "HalogenatedAlkylCarbonCount_Cl": 1},
            0,
            {"HalogenatedPhenolCount_F": 0, "HalogenatedPhenolCount_Cl": 0},
            "CF2Cl: one carbon bonded to both F and Cl => carbon-site markers increment for both types (not mutually exclusive).",
            id="CF2Cl_multilabel_markers",
        ),

        # 11) vinyl chloride: vinylic carbon is non-aromatic => alkyl split
        pytest.param(
            "C=CCl",
            1,
            {"HalogenAtomCount_Cl": 1, "HalogenAtomCount_F": 0, "HalogenAtomCount_Br": 0, "HalogenAtomCount_I": 0},
            1,
            {"HalogenatedCarbonCount_Cl": 1},
            {"HalogenatedAlkylCarbonCount_Cl": 1, "HalogenatedArylCarbonCount_Cl": 0},
            0,
            {"HalogenatedPhenolCount_Cl": 0},
            "Chloroethene: vinylic carbon bonded to Cl counts as halogenated carbon; carbon is not aromatic => alkyl bucket.",
            id="vinyl_chloride_alkyl_split",
        ),

        # 12) biphenyl phenol with Cl on the OTHER ring: halophenol should be 0 (ring-local)
        pytest.param(
            "Oc1ccccc1c2ccccc2Cl",
            1,
            {"HalogenAtomCount_Cl": 1, "HalogenAtomCount_F": 0, "HalogenAtomCount_Br": 0, "HalogenAtomCount_I": 0},
            1,
            {"HalogenatedCarbonCount_Cl": 1},
            {"HalogenatedArylCarbonCount_Cl": 1},
            0,
            {"HalogenatedPhenolCount_Cl": 0},
            "Ring-local halophenol: phenolic OH is on ring A; Cl is on ring B => NOT a halophenol by same-ring definition. "
            "Still one aryl carbon site bonded to Cl overall.",
            id="biphenyl_OH_and_Cl_different_rings",
        ),
    ],
)
def test_halogens_A(
    smiles,
    exp_atoms_total,
    exp_atoms_by,
    exp_carb_total,
    exp_carb_by,
    exp_carb_split,
    exp_ph_total,
    exp_ph_by,
    rationale,
):
    m = _mol(smiles)

    # Halogen atoms
    assert count_halogen_atoms_total(m) == exp_atoms_total, rationale
    _assert_subset(count_halogen_atoms_by_halogen(m), exp_atoms_by, rationale)

    # Halogenated carbon sites (total + by halogen + aromatic/aliphatic split)
    assert count_halogenated_carbons(m) == exp_carb_total, rationale
    _assert_subset(count_halogenated_carbons_by_halogen(m), exp_carb_by, rationale)
    _assert_subset(count_halogenated_carbons_by_halogen_split_aromatic(m), exp_carb_split, rationale)

    # Halophenol OH sites (Option A: class marker)
    assert count_halogenated_phenols(m) == exp_ph_total, rationale
    _assert_subset(count_halogenated_phenols_by_halogen(m), exp_ph_by, rationale)