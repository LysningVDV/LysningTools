"""
RDKit‑based molecular property computations.

This module provides:
    compute_rdkit_descriptors(identifier, id_type)

It converts the identifier to an RDKit Mol and computes a suite of
descriptors. All outputs follow the FLAT naming convention:

    computed_<property>
    source_<property> = "computed"

No experimental values are handled here.
"""

import logging
from typing import Dict, Any

from rdkit import Chem
from rdkit.Chem import (
    Descriptors, Crippen, rdMolDescriptors, Lipinski
)

from physprops.util.normalize import normalize_smiles, normalize_inchi

logger = logging.getLogger(__name__)


# ------------------------------------------------------------
# Identifier → mol
# ------------------------------------------------------------

def _identifier_to_mol(identifier: str, id_type: str):
    """
    Convert identifier of known type into an RDKit Mol.
    RDKit cannot resolve CAS, names, or InChIKeys directly.
    """
    try:
        if id_type == "smiles":
            smi = normalize_smiles(identifier)
            return Chem.MolFromSmiles(smi)

        elif id_type == "inchi":
            inch = normalize_inchi(identifier)
            return Chem.MolFromInchi(inch)

        elif id_type in ("cas", "inchikey", "name"):
            logger.warning(f"RDKit cannot resolve Mol directly from {id_type}.")
            return None

        else:
            logger.warning(f"Unknown identifier type for RDKit: {id_type}")
            return None

    except Exception as e:
        logger.error(f"RDKit failed to convert identifier '{identifier}' ({id_type}): {e}")
        return None


# ------------------------------------------------------------
# Main descriptor computation
# ------------------------------------------------------------

def compute_rdkit_descriptors(identifier: str, id_type: str) -> Dict[str, Any]:
    """
    Compute RDKit descriptors and return as flat fields:

        computed_<property> = value
        source_<property> = "computed"

    If RDKit cannot interpret the molecule, all fields remain None.
    """

    result = {
        # Identifier conversions
        "computed_smiles": None,
        "computed_inchi": None,
        "computed_inchikey": None,

        # Descriptors
        "computed_mw": None,
        "computed_exact_mass": None,
        "computed_clogp": None,
        "computed_tpsa": None,
        "computed_hbd": None,
        "computed_hba": None,
        "computed_rot_bonds": None,
        "computed_ring_count": None,
        "computed_fraction_csp3": None,
        "computed_molar_refractivity": None,

        # Sources
        "source_smiles": None,
        "source_inchi": None,
        "source_inchikey": None,

        "source_mw": None,
        "source_exact_mass": None,
        "source_clogp": None,
        "source_tpsa": None,
        "source_hbd": None,
        "source_hba": None,
        "source_rot_bonds": None,
        "source_ring_count": None,
        "source_fraction_csp3": None,
        "source_molar_refractivity": None,

        "warnings": []
    }

    mol = _identifier_to_mol(identifier, id_type)
    if mol is None:
        result["warnings"].append("RDKit could not generate molecule from identifier.")
        return result

    # -------------------------------
    # Canonical SMILES
    # -------------------------------
    try:
        smi = Chem.MolToSmiles(mol, canonical=True)
        result["computed_smiles"] = smi
        result["source_smiles"] = "computed"
    except Exception as e:
        logger.warning(f"SMILES generation failed: {e}")

    # -------------------------------
    # InChI / InChIKey
    # -------------------------------
    try:
        inchi = Chem.MolToInchi(mol)
        result["computed_inchi"] = inchi
        result["source_inchi"] = "computed"
    except Exception as e:
        logger.warning(f"InChI generation failed: {e}")

    try:
        if result["computed_inchi"]:
            ik = Chem.InchiToInchiKey(result["computed_inchi"])
            result["computed_inchikey"] = ik
            result["source_inchikey"] = "computed"
    except Exception as e:
        logger.warning(f"InChIKey generation failed: {e}")

    # -------------------------------
    # Molecular weight
    # -------------------------------
    try:
        result["computed_mw"] = Descriptors.MolWt(mol)
        result["source_mw"] = "computed"
    except Exception as e:
        logger.warning(f"MW failed: {e}")

    # -------------------------------
    # Exact mass
    # -------------------------------
    try:
        result["computed_exact_mass"] = rdMolDescriptors.CalcExactMolWt(mol)
        result["source_exact_mass"] = "computed"
    except Exception as e:
        logger.warning(f"Exact mass failed: {e}")

    # -------------------------------
    # LogP and molar refractivity
    # -------------------------------
    try:
        result["computed_clogp"] = Crippen.MolLogP(mol)
        result["source_clogp"] = "computed"

        result["computed_molar_refractivity"] = Crippen.MolMR(mol)
        result["source_molar_refractivity"] = "computed"
    except Exception as e:
        logger.warning(f"Crippen properties failed: {e}")

    # -------------------------------
    # TPSA
    # -------------------------------
    try:
        result["computed_tpsa"] = rdMolDescriptors.CalcTPSA(mol)
        result["source_tpsa"] = "computed"
    except Exception as e:
        logger.warning(f"TPSA failed: {e}")

    # -------------------------------
    # HBD / HBA
    # -------------------------------
    try:
        result["computed_hbd"] = Lipinski.NumHDonors(mol)
        result["source_hbd"] = "computed"
    except Exception as e:
        logger.warning(f"HBD failed: {e}")

    try:
        result["computed_hba"] = Lipinski.NumHAcceptors(mol)
        result["source_hba"] = "computed"
    except Exception as e:
        logger.warning(f"HBA failed: {e}")

    # -------------------------------
    # Rotatable bonds
    # -------------------------------
    try:
        result["computed_rot_bonds"] = Lipinski.NumRotatableBonds(mol)
        result["source_rot_bonds"] = "computed"
    except Exception as e:
        logger.warning(f"Rotatable bond calculation failed: {e}")

    # -------------------------------
    # Ring count
    # -------------------------------
    try:
        result["computed_ring_count"] = rdMolDescriptors.CalcNumRings(mol)
        result["source_ring_count"] = "computed"
    except Exception as e:
        logger.warning(f"Ring count failed: {e}")

    # -------------------------------
    # Fraction Csp3
    # -------------------------------
    try:
        result["computed_fraction_csp3"] = rdMolDescriptors.CCalcFractionCSP3(mol) \
            if hasattr(rdMolDescriptors, "CCalcFractionCSP3") \
            else rdMolDescriptors.CalcFractionCSP3(mol)

        result["source_fraction_csp3"] = "computed"
    except Exception as e:
        logger.warning(f"Fraction Csp3 failed: {e}")

    return result