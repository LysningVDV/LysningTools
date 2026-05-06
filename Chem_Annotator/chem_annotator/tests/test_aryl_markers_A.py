import pytest
from chem_annotator.aggregator import features_for_smiles


@pytest.mark.parametrize(
    "smiles, expected_key, expected_value, rationale",
    [
        # -------------------------
        # Ether subtypes
        # -------------------------
        ("COc1ccccc1", "ArylOAlkylEtherCount", 1, "Anisole: Ar–O–alkyl should count (1)."),
        ("CCOc1ccccc1", "ArylOAlkylEtherCount", 1, "Phenetole: Ar–O–alkyl should count (1)."),
        ("c1ccccc1Oc2ccccc2", "ArylOAlkylEtherCount", 0, "Diphenyl ether: Ar–O–Ar should NOT count as Ar–O–alkyl."),
        ("CCOCC", "ArylOAlkylEtherCount", 0, "Aliphatic ether: no aryl group, should NOT count as Ar–O–alkyl."),

        ("COc1ccccc1", "DiarylEtherCount", 0, "Anisole: not a diaryl ether (Ar–O–alkyl)."),
        ("CCOc1ccccc1", "DiarylEtherCount", 0, "Phenetole: not a diaryl ether (Ar–O–alkyl)."),
        ("c1ccccc1Oc2ccccc2", "DiarylEtherCount", 1, "Diphenyl ether: Ar–O–Ar should count as diaryl ether (1)."),
        ("CCOCC", "DiarylEtherCount", 0, "Aliphatic ether: not a diaryl ether."),

        # -------------------------
        # Alkyl phenols (phenolic OH on ring with ≥1 alkyl substituent)
        # -------------------------
        ("Oc1ccccc1", "AlkylPhenolCount", 0, "Phenol: no alkyl substituent on the ring."),
        ("Cc1cccc(O)c1", "AlkylPhenolCount", 1, "Cresol: phenol with methyl substituent => alkyl phenol."),
        ("CCCc1cccc(O)c1", "AlkylPhenolCount", 1, "Propyl phenol: phenol with alkyl substituent => alkyl phenol."),
        ("Clc1cccc(O)c1", "AlkylPhenolCount", 0, "Chlorophenol: halogen is not an alkyl substituent."),
    ],
)
def test_aryl_markers_A(smiles, expected_key, expected_value, rationale):
    feats = features_for_smiles(smiles)
    assert feats["Valid"] == 1, f"{rationale} (SMILES failed to parse?)"
    assert expected_key in feats, f"Missing key in output schema: {expected_key}"
    assert feats[expected_key] == expected_value, (
        f"{rationale} Got={feats[expected_key]!r} Expected={expected_value!r}"
    )