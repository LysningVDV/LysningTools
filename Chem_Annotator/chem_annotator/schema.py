"""
chem_annotator.schema
--------------------
Single source of truth for the output feature schema.

Rules:
- Invalid SMILES must return ALL expected keys.
- Numeric fields default to 0; string fields default to "".
- "Valid" defaults to 0 and is set to 1 only for successfully parsed molecules.

This module intentionally centralizes schema construction so that:
1) aggregator._empty_features() cannot drift from the "real" schema.
2) integration tests can assert schema completeness against one canonical definition.
"""

from __future__ import annotations

from typing import Dict, List, Union

from rdkit import Chem

SCHEMA_VERSION = "1"

def _aldehyde_template_keys() -> List[str]:
    """Return aldehyde sub-keys produced by classify_aldehyde() (stable template expansion)."""
    try:
        # Acetaldehyde should always parse; used only to discover the dict keys.
        tm = Chem.MolFromSmiles("CC=O")
        if tm is None:
            return []
        # Local import avoids any accidental import cycles.
        from .features.aldehydes import classify_aldehyde

        al_counts, _audit = classify_aldehyde(tm)
        return list(al_counts.keys())
    except Exception:
        return []


_ALDEHYDE_KEYS: List[str] = _aldehyde_template_keys()


def make_empty_features() -> Dict[str, Union[int, str]]:
    """
    Return a complete zero/empty schema dict.

    This is the canonical schema constructor and must be used for invalid SMILES.
    """
    d: Dict[str, Union[int, str]] = {
        "SchemaVersion": "",
        "Valid": 0,
        # --- Alcohols ---
        "TotalAlcoholCount": 0,
        "PrimaryAlcoholCount": 0,
        "SecondaryAlcoholCount": 0,
        "TertiaryAlcoholCount": 0,
        "PhenolCount": 0,
        "AlphaHydroxyCarbonylCount": 0,
        "EnolicOHCount": 0,
        "OximeCount": 0,
        "AllylicAlcoholCount": 0,
        "BenzylicAlcoholCount": 0,
        "PropargylicAlcoholCount": 0,
        "AcetalCount": 0,
        "KetalCount": 0,
        "OrthoesterCount": 0,
        "HemiacetalCount": 0,
        "HemiketalCount": 0,
        "Vicinal12DiolCount": 0,
        "OneThreeDiolCount": 0,
        "IsPolyol": 0,
        "AlcoholAudit": "",
        # --- Aldehydes ---
        "AldehydeAudit": "",
        # --- Ethers / Carbonyls / Esters ---
        "EtherCount": 0,
        "EtherCount_Total": 0,
        "EtherCount_Acyclic": 0,
        "EtherCount_Cyclic": 0,
        "EpoxideCount": 0,
        "EtherAliphaticCount": 0,
        "EtherAromaticCount": 0,
        "EtherMixedCount": 0,
        "EtherRingCount": 0,
        "KetoneCount": 0,
        "EsterCount_Total": 0,
        "EsterCount_Open": 0,
        "LactoneCount": 0,
        "AcrylateEsterCount": 0,
        "MethacrylateEsterCount": 0,
        "CarboxylicAcidCount": 0,
        "CarboxylicAcidCount_Fragment": 0,
        # --- Sulfur ---
        "ThiolCount": 0,
        "ThiophenolCount": 0,
        "AliphaticThiolCount": 0,
        "DisulfideCount": 0,
        "ThioesterCount": 0,
        "ThioetherCount": 0,
        "SulfoxideCount": 0,
        "SulfoneCount": 0,
        "Thiophenol_OrthoCount": 0,
        "Thiophenol_MetaCount": 0,
        "Thiophenol_ParaCount": 0,
        # --- Malonates ---
        "MalonateLikeCount": 0,
        "MalonateDiesterCount": 0,
        "MalonateHalfEsterCount": 0,
        "MalonicAcidCount": 0,
        # --- Halogens (legacy totals) ---
        "HalogenatedPhenolCount": 0,
        "HalogenatedCarbonCount": 0,
        # --- Aromatics / heterocycles ---
        "PyridineCount": 0,
        "ThiazoleCount": 0,
        "IndoleCount": 0,
        "FuranCount": 0,
        "ThiopheneCount": 0,
        "TerpeneLikeUnitCount": 0,
        # --- Nitro ---
        "NitroGroupCount": 0,
        "ImineCount": 0,
        "AmideCount_Total": 0,
        "LactamCount": 0,
        "UreaCount": 0,
        "UrethaneCount": 0,
        "IsocyanateCount": 0,
        # --- Nitriles ---
        "NitrileCount": 0,
        "NitrileFragmentCount": 0,
        # --- Macro musks ---
        "MacroMusks_Total": 0,
        "MacroMusks_Ketones": 0,
        "MacroMusks_Lactones": 0,
        # --- Amines ---
        "AmineCount_Total": 0,
        "AmineCount_Primary": 0,
        "AmineCount_Secondary": 0,
        "AmineCount_Tertiary": 0,
        # --- Rings & unsaturation ---
        "NumAromaticAtoms": 0,
        "NumAromaticRings": 0,
        "NumAliphaticRings": 0,
        "NumRingsTotal": 0,
        "NumUnsaturatedBonds": 0,
        "NumUnsaturatedBonds_All": 0,
        "IsFullySaturated": 0, 
        "NumAlkeneBonds": 0,
        "NumAlkyneBonds": 0,
        "IsPureHydrocarbon": 0,
        "CarbonAtomCount": 0,
        "IsHydrocarbonAromatic": 0,
        "IsHydrocarbonAliphatic": 0,
        "HydrocarbonRingCount": 0,
        "IsTerpeneHydrocarbon": 0,
        "ArylOAlkylEtherCount": 0,
        "DiarylEtherCount": 0,
        "AlkylPhenolCount": 0,

        # --- Totals for S and N ---
        "TotalNitrogenAtomCount": 0,
        "TotalSulfurAtomCount": 0,
        "TotalSulfurGroupCount": 0,
        "TotalNitrogenGroupCount": 0,
        # --- High-impact tiers ---
        "HighImpactTier1Count": 0,
        "HighImpactTier2Count": 0,
        "HighImpactSummary": "",
    }

    # Aldehyde dict expanded via **al_counts in valid rows => include those keys as numeric zeros.
    for k in _ALDEHYDE_KEYS:
        d[k] = 0

    # Halogen subtype keys (new)
    d["HalogenAtomCount_Total"] = 0
    for lbl in ("F", "Cl", "Br", "I"):
        d[f"HalogenAtomCount_{lbl}"] = 0
        d[f"HalogenatedCarbonCount_{lbl}"] = 0
        d[f"HalogenatedArylCarbonCount_{lbl}"] = 0
        d[f"HalogenatedAlkylCarbonCount_{lbl}"] = 0
        d[f"HalogenatedPhenolCount_{lbl}"] = 0

    return d


# Canonical constants (safe for tests/consumers)
FEATURE_DEFAULTS: Dict[str, Union[int, str]] = make_empty_features()
FEATURE_KEYS = tuple(FEATURE_DEFAULTS.keys())