import pytest
from rdkit import Chem

from chem_annotator.features.sulfur import (
    count_thiols,
    count_aliphatic_thiols,
    count_thiophenols,
    count_disulfides,
    count_thioesters,
    count_thioethers_excluding_thioesters,
    count_sulfoxides,
    count_sulfones,
    classify_thiophenol_positions,
)


def _mol(smiles: str) -> Chem.Mol:
    m = Chem.MolFromSmiles(smiles)
    assert m is not None, f"RDKit failed to parse SMILES: {smiles}"
    return m


# B-suite intent (edge/exclusions):
# - Thioethers must exclude thioesters (mutually exclusive).
# - Thioethers should NOT be excluded merely because a carbonyl exists elsewhere in the molecule
#   (only exclude if sulfur is directly attached to an acyl carbon as in a thioester).
# - Sulfoxide must not count sulfones (regression guard).
# - Thiophenol positional classification uses a single-bucket elif priority (o > m > p) and
#   is ring-local to the ring containing the aromatic carbon bonded to SH.

@pytest.mark.parametrize(
    "smiles, exp, rationale",
    [
        # 1) Thioether adjacent to carbonyl elsewhere (should still be a thioether)
        # 3-(methylthio)propanal: O=CH-CH2-CH2-S-CH3
        # Sulfur is NOT bound to carbonyl carbon; it's a true thioether.
        pytest.param(
            "O=CCCSC",
            {
                "thioesters": 0,
                "thioethers": 1,
            },
            "Thioether adjacent to aldehyde: sulfur is not directly attached to an acyl carbon, so should remain thioether=1; thioester=0.",
            id="thioether_adjacent_to_aldehyde_not_thioester",
        ),

        # 2) True thioester must NOT be counted as thioether (mutual exclusion)
        pytest.param(
            "CC(=O)SC",
            {
                "thioesters": 1,
                "thioethers": 0,
            },
            "Thioester R-C(=O)-S-R': should be thioester=1 and excluded from thioether.",
            id="thioester_excludes_thioether",
        ),

        # 3) Another thioester (variant): still excluded from thioether
        pytest.param(
            "CCC(=O)SC",
            {
                "thioesters": 1,
                "thioethers": 0,
            },
            "Another thioester: sulfur directly bonded to carbonyl carbon => thioester=1; thioether must remain 0.",
            id="thioester_variant_excludes_thioether",
        ),

        # 4) Sulfoxide should count 1; sulfone should be 0 (guard)
        pytest.param(
            "CCS(=O)CC",
            {
                "sulfoxides": 1,
                "sulfones": 0,
            },
            "Dialkyl sulfoxide: S(=O) with two carbon substituents => sulfoxide=1; not sulfone.",
            id="sulfoxide_not_sulfone",
        ),

        # 5) Sulfone should count 1; sulfoxide should be 0 (regression guard after fix)
        pytest.param(
            "CCS(=O)(=O)CC",
            {
                "sulfoxides": 0,
                "sulfones": 1,
            },
            "Dialkyl sulfone: S(=O)2 with two carbon substituents => sulfone=1; should not count as sulfoxide.",
            id="sulfone_not_sulfoxide",
        ),

        # 6) Thiolate (deprotonated) should not be counted as thiol (S has no H)
        pytest.param(
            "C[S-]",
            {
                "thiols": 0,
                "aliph_thiols": 0,
                "thiophenols": 0,
            },
            "Thiolate anion: no S-H present => should not be counted as thiol/thiophenol/aliphatic thiol.",
            id="thiolate_not_thiol",
        ),

        # 7) Ortho-substituted thiophenol: o-bromo thiophenol => ortho bucket
        pytest.param(
            "Sc1ccccc1Br",
            {
                "thiophenols": 1,
                "pos": (1, 0, 0),
            },
            "o-bromobenzenethiol: SH on aromatic carbon; ortho position substituted (Br) => ortho=1.",
            id="thiophenol_ortho_sub",
        ),

        # 8) Meta-substituted thiophenol: m-bromo thiophenol => meta bucket
        pytest.param(
            "Sc1cccc(Br)c1",
            {
                "thiophenols": 1,
                "pos": (0, 1, 0),
            },
            "m-bromobenzenethiol: meta position substituted => meta=1.",
            id="thiophenol_meta_sub",
        ),

        # 9) Para-substituted thiophenol: p-bromo thiophenol => para bucket
        pytest.param(
            "Sc1ccc(Br)cc1",
            {
                "thiophenols": 1,
                "pos": (0, 0, 1),
            },
            "p-bromobenzenethiol: para position substituted => para=1.",
            id="thiophenol_para_sub",
        ),

        # 10) Multi-substituted thiophenol (ortho + para): should fall into ortho due to elif priority
        pytest.param(
            "Sc1ccc(Br)cc1Cl",
            {
                "thiophenols": 1,
                "pos": (1, 0, 0),
            },
            "Thiophenol with multiple ring substituents: o and p substituted. Classifier uses priority (o > m > p), so should record ortho only.",
            id="thiophenol_multi_sub_priority_to_ortho",
        ),
    ],
)
def test_sulfur_B(smiles, exp, rationale):
    m = _mol(smiles)

    # Only assert keys that matter per case (subset assertions keep this suite tight and diagnostic)
    if "thiols" in exp:
        assert count_thiols(m) == exp["thiols"], rationale
    if "aliph_thiols" in exp:
        assert count_aliphatic_thiols(m) == exp["aliph_thiols"], rationale
    if "thiophenols" in exp:
        assert count_thiophenols(m) == exp["thiophenols"], rationale

    if "disulfides" in exp:
        assert count_disulfides(m) == exp["disulfides"], rationale
    if "thioesters" in exp:
        assert count_thioesters(m) == exp["thioesters"], rationale
    if "thioethers" in exp:
        assert count_thioethers_excluding_thioesters(m) == exp["thioethers"], rationale

    if "sulfoxides" in exp:
        assert count_sulfoxides(m) == exp["sulfoxides"], rationale
    if "sulfones" in exp:
        assert count_sulfones(m) == exp["sulfones"], rationale

    if "pos" in exp:
        assert classify_thiophenol_positions(m) == exp["pos"], rationale