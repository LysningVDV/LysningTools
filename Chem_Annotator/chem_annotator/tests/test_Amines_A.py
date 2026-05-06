import pytest
from chem_annotator.aggregator import features_for_smiles


@pytest.mark.parametrize(
    "smiles, exp_total, exp_p, exp_s, exp_t, rationale",
    [
        # -------------------------
        # Explicit positives from your real-world list
        # -------------------------
        ("CN(C)C", 1, 0, 0, 1, "Trimethylamine: true tertiary amine => tertiary=1."),
        ("OCCN(CCO)CCO", 1, 0, 0, 1, "Triethanolamine: true tertiary amine => tertiary=1."),

        # -------------------------
        # Real-world false-positive regressions (should NOT be counted as amines)
        # -------------------------
        ("CC(=O)c1ccccn1", 0, 0, 0, 0, "Aryl ketone + pyridine N: aromatic ring N is not an amine."),
        ("CC(=O)c1cnccn1", 0, 0, 0, 0, "Diazine ring N: aromatic ring N is not an amine."),
        ("CC(=O)c1nccs1", 0, 0, 0, 0, "Thiazole-like aromatic N: not an amine."),
        ("COCc1cnccn1", 0, 0, 0, 0, "Diazine: aromatic ring N is not an amine."),
        ("COCc1cnccn1", 0, 0, 0, 0, "Diazine duplicate: should still be 0."),
        ("Cc1cnccn1", 0, 0, 0, 0, "Diazine: aromatic ring N is not an amine."),
        ("c1cnccn1", 0, 0, 0, 0, "Diazine: aromatic ring N is not an amine."),
        ("c1ccncc1", 0, 0, 0, 0, "Pyridine: aromatic ring N is not an amine."),

        ("N#CC(=C1CCCCC1)c1ccccc1", 0, 0, 0, 0, "Nitrile: N#C is not an amine."),
        ("CCCCCCCCCCCC#N", 0, 0, 0, 0, "Long-chain nitrile: N#C is not an amine."),
        ("CCCCCCCC#N", 0, 0, 0, 0, "Nitrile: N#C is not an amine."),
        ("CCCCCCCCCCC=CC#N", 0, 0, 0, 0, "Unsaturated nitrile: N#C is not an amine."),
        ("CCCCCC/C=C\\C#N", 0, 0, 0, 0, "Alkenyl nitrile: N#C is not an amine."),
        ("CCC(C)=CCCC(C)=CC#N", 0, 0, 0, 0, "Diene nitrile: N#C is not an amine."),
        ("N#C/C=C/c1ccccc1", 0, 0, 0, 0, "Aryl alkenyl nitrile: N#C is not an amine."),
        ("C/C(=C/C#N)CCc1ccccc1", 0, 0, 0, 0, "Substituted nitrile: N#C is not an amine."),
        ("CC1CC(C)(C)CC1=CC#N", 0, 0, 0, 0, "Ring nitrile: N#C is not an amine."),
        ("CC(=CC#N)CC(C)CC(C)C", 0, 0, 0, 0, "Aliphatic nitrile: N#C is not an amine."),
        ("CC(C)CC(C)CC(C)CC#N", 0, 0, 0, 0, "Aliphatic nitrile: N#C is not an amine."),
        ("CCCCCCCCCCCCCC#N", 0, 0, 0, 0, "Long nitrile: N#C is not an amine."),

        ("c1ccc2[nH]ccc2c1", 0, 0, 0, 0, "Indole: [nH] aromatic pyrrolic N is not an amine."),
        ("Cc1c[nH]c2ccccc12", 0, 0, 0, 0, "Indole-like not an amine."),
        ("CC(=O)c1ccc[nH]1", 0, 0, 0, 0, "Aromatic [nH] ring: not an amine."),

        ("CC12CCCC(C)(CC1)C2=NO", 0, 0, 0, 0, "Oxime (=NO): not an amine."),
        ("CCC(CC(C)CC)=NO", 0, 0, 0, 0, "Oxime (=NO): not an amine."),
        ("ON=CCc1ccccc1", 0, 0, 0, 0, "Oxime-like ON=...: not an amine."),

        # Multi-fragment SMILES: should still not contribute to amines
        ("CCc1cnc(C)cn1.CCc1cncc(C)n1", 0, 0, 0, 0, "Two heteroaromatics (dot-disconnected): still no amine."),
    ],
)
def test_amines_realworld_regressions_A(smiles, exp_total, exp_p, exp_s, exp_t, rationale):
    feats = features_for_smiles(smiles)
    assert feats["Valid"] == 1, f"{rationale} (SMILES failed to parse?)"

    assert feats["AmineCount_Total"] == exp_total, (
        f"{rationale} Total Got={feats['AmineCount_Total']!r} Expected={exp_total!r}"
    )
    assert feats["AmineCount_Primary"] == exp_p, (
        f"{rationale} Primary Got={feats['AmineCount_Primary']!r} Expected={exp_p!r}"
    )
    assert feats["AmineCount_Secondary"] == exp_s, (
        f"{rationale} Secondary Got={feats['AmineCount_Secondary']!r} Expected={exp_s!r}"
    )
    assert feats["AmineCount_Tertiary"] == exp_t, (
        f"{rationale} Tertiary Got={feats['AmineCount_Tertiary']!r} Expected={exp_t!r}"
    )