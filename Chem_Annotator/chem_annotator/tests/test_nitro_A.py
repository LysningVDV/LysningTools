import pytest
from rdkit import Chem

from chem_annotator.features.nitro import (
    count_nitro_groups,
    count_imines,
    count_amides,
    count_lactams,
    count_ureas,
    count_urethanes,
    count_isocyanates,
)


def _mol(smiles: str) -> Chem.Mol:
    m = Chem.MolFromSmiles(smiles)
    assert m is not None, f"RDKit failed to parse SMILES: {smiles}"
    return m


# -------------------------
# Nitro group detection
# -------------------------
# Overlap / counting rules (explicit):
# - Nitro is defined as the charge-separated motif [N+](=O)[O-].
# - One nitro group => count 1. Multiple nitro groups => additive.
# - Nitroso (R–N=O) and nitrites (RON=O) are NOT nitro and should not be counted. [1](https://lysninginnovationconsultant-my.sharepoint.com/personal/villeneuve_lysning_nl/Documents/Microsoft%20Copilot%20Chat%20Files/test_nitro_A.py)

@pytest.mark.parametrize(
    "smiles, expected, rationale",
    [
        # 1) Nitromethane
        ("C[N+](=O)[O-]", 1, "Nitromethane: one [N+](=O)[O-] nitro group => 1."),
        # 2) Nitroethane
        ("CC[N+](=O)[O-]", 1, "Nitroethane: one nitro group => 1."),
        # 3) 1-nitropropane
        ("CCC[N+](=O)[O-]", 1, "1-nitropropane: one nitro group => 1."),
        # 4) Nitrobenzene
        ("O=[N+]([O-])c1ccccc1", 1, "Nitrobenzene: one nitro substituent => 1."),
        # 5) p-nitrotoluene
        ("Cc1ccc([N+](=O)[O-])cc1", 1, "p-nitrotoluene: one nitro substituent => 1."),
        # 6) 1,3-dinitrobenzene
        ("O=[N+]([O-])c1cccc([N+](=O)[O-])c1", 2, "Dinitrobenzene: two nitro groups => 2 (additive)."),
        # 7) TNT (2,4,6-trinitrotoluene)
        ("Cc1c([N+](=O)[O-])cc([N+](=O)[O-])cc1[N+](=O)[O-]", 3, "TNT: three nitro groups => 3 (additive)."),
        # 8) Nitro + aldehyde (nitro count unaffected)
        ("O=CCc1ccc([N+](=O)[O-])cc1", 1, "Aldehyde + nitro: one nitro group => 1."),
        # 9) Nitro + halogen (nitro count unaffected)
        ("Clc1ccc([N+](=O)[O-])cc1", 1, "Chloronitrobenzene: one nitro group => 1."),
        # 10) Nitrosomethane is NOT nitro
        ("CN=O", 0, "Nitroso (R–N=O) is not [N+](=O)[O-] => 0."),
    ],
)
def test_nitro_A(smiles, expected, rationale):
    m = _mol(smiles)
    got = count_nitro_groups(m)
    assert got == expected, rationale


# -------------------------
# Imines (C=N) detection
# -------------------------
# Semantics:
# - Count C=N double bonds where C is carbon (6) and N is nitrogen (7).
# - Include aromatic-carbon imines, but exclude cases where the nitrogen itself is aromatic.
# - Exclude amide-like contexts (N attached to carbonyl carbon).
# - Oximes (C=N-O) should NOT be counted as imines (tracked separately as OximeCount elsewhere). [1](https://lysninginnovationconsultant-my.sharepoint.com/personal/villeneuve_lysning_nl/Documents/Microsoft%20Copilot%20Chat%20Files/test_nitro_A.py)

@pytest.mark.parametrize(
    "smiles, expected, rationale",
    [
        ("CCN=CC", 1, "Simple imine C=N => 1."),
        ("c1ccccc1C=NCC", 1, "Aryl imine: aromatic carbon allowed; N not aromatic => 1."),
        ("n1ccccc1", 0, "Aromatic ring nitrogen is not an imine => 0."),
        ("CC(=O)NCC", 0, "Amide N attached to carbonyl carbon => excluded from ImineCount => 0."),
        ("CC=NO", 0, "Oxime (C=N-O) must not contribute to ImineCount => 0."),
    ],
)
def test_imines_A(smiles, expected, rationale):
    m = _mol(smiles)
    got = count_imines(m)
    assert got == expected, rationale


# -------------------------
# Amides & lactams (separate)
# -------------------------
# - AmideCount_Total: carboxamides only (C(=O)-N) with exactly one N neighbor and no C(=O)-O on same carbonyl carbon.
# - LactamCount: subset where the acyl C–N bond is in a ring (cyclic amide).
# - Excludes carbamates/urethanes (C(=O)-O present) and excludes urea-like carbonyls (two N neighbors). [1](https://lysninginnovationconsultant-my.sharepoint.com/personal/villeneuve_lysning_nl/Documents/Microsoft%20Copilot%20Chat%20Files/test_nitro_A.py)

@pytest.mark.parametrize(
    "smiles, exp_amide, rationale",
    [
        ("CC(=O)N", 1, "Acetamide: one carboxamide => AmideCount_Total=1."),
        ("CC(=O)N(C)C", 1, "N,N-dimethylacetamide: one carboxamide => AmideCount_Total=1."),
        ("O=C1NCCCCC1", 1, "Caprolactam is an amide too => AmideCount_Total=1."),
        ("CCOC(=O)N", 0, "Carbamate/urethane has C(=O)-O => excluded from AmideCount_Total."),
        ("NC(=O)N", 0, "Urea-like carbonyl has two N neighbors => excluded from AmideCount_Total."),
        ("O=C1OCCC1", 0, "Lactone is an ester => excluded from amide counting."),
    ],
)
def test_amides_A(smiles, exp_amide, rationale):
    m = _mol(smiles)
    got = count_amides(m)
    assert got == exp_amide, rationale


@pytest.mark.parametrize(
    "smiles, exp_lactam, rationale",
    [
        ("CC(=O)N", 0, "Acetamide is not cyclic => LactamCount=0."),
        ("O=C1NCCCCC1", 1, "Caprolactam is a cyclic amide => LactamCount=1."),
        ("O=C1NCCCC1", 1, "2-piperidone (lactam) => LactamCount=1."),
        ("CCOC(=O)N", 0, "Carbamate/urethane excluded => LactamCount=0."),
        ("NC(=O)N", 0, "Urea is not a lactam => LactamCount=0."),
    ],
)
def test_lactams_A(smiles, exp_lactam, rationale):
    m = _mol(smiles)
    got = count_lactams(m)
    assert got == exp_lactam, rationale


# -------------------------
# Ureas detection
# -------------------------
# - Urea site = carbonyl carbon with exactly two single-bond nitrogen neighbors (N-C(=O)-N)
# - Excludes carbamates/urethanes (C(=O)-O present)
# - Counts one per urea carbonyl [1](https://lysninginnovationconsultant-my.sharepoint.com/personal/villeneuve_lysning_nl/Documents/Microsoft%20Copilot%20Chat%20Files/test_nitro_A.py)

@pytest.mark.parametrize(
    "smiles, expected, rationale",
    [
        ("NC(=O)N", 1, "Urea: one N-C(=O)-N carbonyl => 1."),
        ("CNC(=O)NC", 1, "Dialkyl urea: one urea carbonyl => 1."),
        ("O=C1NCCN1", 1, "Cyclic urea (imidazolidin-2-one): still a urea carbonyl => 1."),
        ("CC(=O)NCC", 0, "Amide has only one N neighbor => not urea => 0."),
        ("CCOC(=O)N", 0, "Carbamate/urethane has C(=O)-O => excluded => 0."),
    ],
)
def test_ureas_A(smiles, expected, rationale):
    m = _mol(smiles)
    got = count_ureas(m)
    assert got == expected, rationale

# -------------------------
# Urethanes / carbamates detection
# -------------------------
# - Urethane site = carbonyl carbon with >=1 single-bond O neighbor AND >=1 single-bond N neighbor (O-C(=O)-N)
# - Counts one per urethane carbonyl
# - Distinct from amide (no C-O single) and from urea (two N neighbors, no C-O single)

@pytest.mark.parametrize(
    "smiles, expected, rationale",
    [
        ("CCOC(=O)N", 1, "Ethyl carbamate: one O-C(=O)-N site => 1."),
        ("COC(=O)NC", 1, "Methyl N-methylcarbamate: one urethane site => 1."),
        ("CC(=O)NCC", 0, "Amide has no single-bond O on carbonyl carbon => not urethane => 0."),
        ("NC(=O)N", 0, "Urea has no single-bond O on carbonyl carbon => not urethane => 0."),
        ("CC(=O)OC", 0, "Ester has C-O single but no N neighbor => not urethane => 0."),
    ],
)
def test_urethanes_A(smiles, expected, rationale):
    m = _mol(smiles)
    got = count_urethanes(m)
    assert got == expected, rationale

# -------------------------
# Isocyanates detection
# -------------------------
# - Isocyanate site = N=C=O
# - Counts one per N=C=O group
# - Distinct from urea/urethane/amide/nitrile motifs

@pytest.mark.parametrize(
    "smiles, expected, rationale",
    [
        ("O=C=N", 1, "Isocyanic acid motif written as O=C=N still contains N=C=O => 1."),
        ("CN=C=O", 1, "Methyl isocyanate: one N=C=O => 1."),
        ("O=C(N)N", 0, "Urea (or urea-like) is not N=C=O => 0."),
        ("CCOC(=O)N", 0, "Urethane/carbamate is not N=C=O => 0."),
        ("N#CC", 0, "Nitrile is not isocyanate => 0."),
    ],
)
def test_isocyanates_A(smiles, expected, rationale):
    m = _mol(smiles)
    got = count_isocyanates(m)
    assert got == expected, rationale