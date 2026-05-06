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


@pytest.mark.parametrize(
    "smiles, exp, rationale",
    [
        # 1) Ethanethiol: one aliphatic thiol
        (
            "CCS",
            {
                "thiols": 1,
                "aliph_thiols": 1,
                "thiophenols": 0,
                "disulfides": 0,
                "thioesters": 0,
                "thioethers": 0,
                "sulfoxides": 0,
                "sulfones": 0,
                "pos": (0, 0, 0),
            },
            "Ethanethiol: one S–H attached to non-aromatic carbon => thiol=1, aliphatic=1, thiophenol=0.",
        ),

        # 2) Thiophenol: aromatic thiol
        (
            "c1ccccc1S",
            {
                "thiols": 1,
                "aliph_thiols": 0,
                "thiophenols": 1,
                "disulfides": 0,
                "thioesters": 0,
                "thioethers": 0,
                "sulfoxides": 0,
                "sulfones": 0,
                "pos": (0, 0, 0),  # unsubstituted: no o/m/p substituent
            },
            "Thiophenol: S–H attached to aromatic carbon => thiophenol=1 (aromatic thiol). No ring substitution => no o/m/p.",
        ),

        # 3) p-methyl thiophenol: para-substituted thiophenol (para bucket)
        (
            "Cc1ccc(S)cc1",
            {
                "thiols": 1,
                "aliph_thiols": 0,
                "thiophenols": 1,
                "disulfides": 0,
                "thioesters": 0,
                "thioethers": 0,
                "sulfoxides": 0,
                "sulfones": 0,
                "pos": (0, 0, 1),
            },
            "p-thiocresol: thiophenol with a para methyl substituent => para=1 (o/m are false).",
        ),

        # 4) Dimethyl sulfide: thioether
        (
            "CSC",
            {
                "thiols": 0,
                "aliph_thiols": 0,
                "thiophenols": 0,
                "disulfides": 0,
                "thioesters": 0,
                "thioethers": 1,
                "sulfoxides": 0,
                "sulfones": 0,
                "pos": (0, 0, 0),
            },
            "Dimethyl sulfide: R–S–R with S degree 2 and both neighbors carbon => thioether=1.",
        ),

        # 5) Diphenyl sulfide: aromatic thioether
        (
            "c1ccccc1Sc2ccccc2",
            {
                "thiols": 0,
                "aliph_thiols": 0,
                "thiophenols": 0,
                "disulfides": 0,
                "thioesters": 0,
                "thioethers": 1,
                "sulfoxides": 0,
                "sulfones": 0,
                "pos": (0, 0, 0),
            },
            "Diphenyl sulfide: S degree 2 with two carbon neighbors => thioether=1 (not a thiol).",
        ),

        # 6) Diethyl disulfide: one S–S bond
        (
            "CCSSCC",
            {
                "thiols": 0,
                "aliph_thiols": 0,
                "thiophenols": 0,
                "disulfides": 1,
                "thioesters": 0,
                "thioethers": 0,
                "sulfoxides": 0,
                "sulfones": 0,
                "pos": (0, 0, 0),
            },
            "Diethyl disulfide: contains exactly one S–S bond => disulfides=1.",
        ),

        # 7) Thioester: methyl thioacetate (CH3-C(=O)-S-CH3)
        (
            "CC(=O)SC",
            {
                "thiols": 0,
                "aliph_thiols": 0,
                "thiophenols": 0,
                "disulfides": 0,
                "thioesters": 1,
                "thioethers": 0,
                "sulfoxides": 0,
                "sulfones": 0,
                "pos": (0, 0, 0),
            },
            "Methyl thioacetate: R–C(=O)–S–R' => thioester=1; must be excluded from thioethers.",
        ),

        # 8) Sulfoxide: dimethyl sulfoxide
        (
            "CS(=O)C",
            {
                "thiols": 0,
                "aliph_thiols": 0,
                "thiophenols": 0,
                "disulfides": 0,
                "thioesters": 0,
                "thioethers": 0,
                "sulfoxides": 1,
                "sulfones": 0,
                "pos": (0, 0, 0),
            },
            "DMSO: matches sulfoxide SMARTS S(=O)(C)C => sulfoxide=1.",
        ),

        # 9) Sulfone: dimethyl sulfone
        (
            "CS(=O)(=O)C",
            {
                "thiols": 0,
                "aliph_thiols": 0,
                "thiophenols": 0,
                "disulfides": 0,
                "thioesters": 0,
                "thioethers": 0,
                "sulfoxides": 0,
                "sulfones": 1,
                "pos": (0, 0, 0),
            },
            "Dimethyl sulfone: matches sulfone SMARTS S(=O)(=O)(C)C => sulfone=1; should not be sulfoxide.",
        ),

        # 10) Benzyl mercaptan: thiol attached to benzylic (non-aromatic) carbon => aliphatic thiol
        (
            "c1ccccc1CS",
            {
                "thiols": 1,
                "aliph_thiols": 1,
                "thiophenols": 0,
                "disulfides": 0,
                "thioesters": 0,
                "thioethers": 0,
                "sulfoxides": 0,
                "sulfones": 0,
                "pos": (0, 0, 0),
            },
            "Benzyl mercaptan: S–H attached to benzylic sp3 carbon (non-aromatic) => aliphatic thiol, not thiophenol.",
        ),
    ],
)
def test_sulfur_A(smiles, exp, rationale):
    m = _mol(smiles)

    assert count_thiols(m) == exp["thiols"], rationale
    assert count_aliphatic_thiols(m) == exp["aliph_thiols"], rationale
    assert count_thiophenols(m) == exp["thiophenols"], rationale

    assert count_disulfides(m) == exp["disulfides"], rationale
    assert count_thioesters(m) == exp["thioesters"], rationale
    assert count_thioethers_excluding_thioesters(m) == exp["thioethers"], rationale

    assert count_sulfoxides(m) == exp["sulfoxides"], rationale
    assert count_sulfones(m) == exp["sulfones"], rationale

    assert classify_thiophenol_positions(m) == exp["pos"], rationale