# test_chem_patterns_A.py
import pytest
from rdkit import Chem

import chem_annotator.chem_patterns as cp


def _mol(smiles: str) -> Chem.Mol:
    """Parse SMILES for tests; fail fast if RDKit can't parse."""
    m = Chem.MolFromSmiles(smiles)
    assert m is not None, f"RDKit failed to parse SMILES: {smiles}"
    return m


def test_all_smarts_parsed_into_patts():
    """
    Core hygiene: every SMARTS string in SMARTS should parse into a Mol in PATTS.
    If not, downstream modules will silently miss descriptors.
    """
    missing = sorted(set(cp.SMARTS) - set(cp.PATTS))
    assert not missing, f"These SMARTS keys did not parse into PATTS: {missing}"


@pytest.mark.parametrize(
    "smiles,expected",
    [
        # Ethanol: classic alcohol OH attached to aliphatic carbon -> should match OH finder.
        pytest.param("CCO", True, id="OH_ethanol_matches"),
        # Phenol: OH attached to aromatic carbon -> should match OH finder.
        pytest.param("c1ccccc1O", True, id="OH_phenol_matches"),
        # Acetic acid: HO is attached to carbonyl carbon; should NOT be treated as alcohol/phenol OH.
        # (If you intend OH_PATT to be a generic hydroxyl finder, change this expectation.)
        pytest.param("CC(=O)O", False, id="OH_carboxylic_acid_should_not_match"),
    ],
)
def test_oh_patt_is_mol_and_matches_expected(smiles, expected):
    """
    IUPAC/convention logic:
      - Alcohol/phenol OH: O–C(sp3) or O–c(aromatic) should match.
      - Carboxylic acid OH is NOT an alcohol; it should be excluded at the OH-pattern level
        if OH_PATT is meant to feed alcohol counting.
    """
    assert isinstance(cp.OH_PATT, Chem.Mol), "OH_PATT must be an RDKit Mol (not a tuple or None)."
    m = _mol(smiles)
    assert m.HasSubstructMatch(cp.OH_PATT) is expected


@pytest.mark.parametrize(
    "patt_name,smiles,expected",
    [
        # --- Carbonyl families ---
        # Aldehyde SMARTS is [CX3H1](=O)[#6]: acetaldehyde has CHO attached to carbon -> True.
        pytest.param("Aldehyde", "CC=O", True, id="aldehyde_acetaldehyde_pos"),
        # Formaldehyde (C=O) is not attached to carbon -> False by this SMARTS (intentional exclusion).
        pytest.param("Aldehyde", "C=O", False, id="aldehyde_formaldehyde_neg"),
        # Ketone SMARTS is [#6][CX3](=O)[#6]: acetone has two carbon substituents -> True.
        pytest.param("Ketone", "CC(=O)C", True, id="ketone_acetone_pos"),
        # Aldehyde should not match ketone pattern (only one carbon substituent + H).
        pytest.param("Ketone", "CC=O", False, id="ketone_should_not_match_aldehyde"),
        # Ester SMARTS: R-C(=O)-O-R'
        pytest.param("Ester", "CC(=O)OC", True, id="ester_methyl_acetate_pos"),
        # Carboxylic acid SMARTS: C(=O)OH
        pytest.param("CarboxylicAcid", "CC(=O)O", True, id="carboxylic_acid_acetic_acid_pos"),

        # --- Ethers ---
        # Aliphatic ether: O (not ring) between two sp3 carbons -> True for diethyl ether.
        pytest.param("Ether_Aliphatic", "CCOCC", True, id="ether_aliphatic_diethyl_ether_pos"),
        # Mixed ether: one aromatic + one aliphatic carbon -> True for anisole.
        pytest.param("Ether_Mixed", "COc1ccccc1", True, id="ether_mixed_anisole_pos"),
        # Negative control: if 'Ether' is meant to represent IUPAC ethers (R-O-R),
        # it should NOT match the alkoxy oxygen of an ester.
        pytest.param("Ether", "CC(=O)OC", False, id="ether_generic_should_not_count_ester"),
    ],
)
def test_core_smarts_patterns(patt_name, smiles, expected):
    """
    Overlap rules (explicit):
      - Aldehyde vs Ketone are mutually exclusive by definition for a given carbonyl carbon.
      - Ester should NOT be counted as CarboxylicAcid.
      - Ether subtype patterns (Aliphatic/Mixed/Ring/Aromatic) may overlap with a generic Ether pattern
        only if generic Ether is truly intended as "any D2 oxygen". Here we assert IUPAC ether logic:
        esters are NOT ethers.
    """
    patt = cp.PATTS[patt_name]
    m = _mol(smiles)
    assert m.HasSubstructMatch(patt) is expected