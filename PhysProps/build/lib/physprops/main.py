"""
Main integration module for the Physical Properties Retrieval App.

Implements:
- Per-row multi-identifier fallback (Priority B)
- Strict identifier validation
- Column-name + pattern-based candidate detection
- Combined results: experimental/computed/final with sources
- CLI interface
- High-level resolve_dataframe()

Priority Order B for identifiers:
    SMILES > InChI > InChIKey > CAS > Name
"""

import argparse
import datetime
import logging
from typing import Dict, Any, List, Optional

import pandas as pd
from rdkit import Chem

from physprops.util.identify import normalize_identifier, detect_identifier_type
from physprops.util.normalize import clean_whitespace, normalize_cas
from physprops.sources.pubchem import get_pubchem_properties
from physprops.compute.rdkit import compute_rdkit_descriptors
from physprops.sources.fallbacks import apply_fallbacks
from physprops.io.excel_io import (
    load_excel,
    save_excel,
    integrate_results_into_dataframe
)

logger = logging.getLogger(__name__)

# ------------------------------------------------------------
# Column name patterns (Option B: name + content detection)
# ------------------------------------------------------------

COLNAME_PATTERNS = {
    "smiles": ["smiles", "structure", "struct", "smile"],
    "inchi": ["inchi", "inchi string"],
    "inchikey": ["inchikey", "inchi key"],
    "cas": ["cas", "cas no", "cas number", "cas nr"],
    "name": ["name", "chemical", "substance", "compound"]
}

PRIORITY_ORDER = ["smiles", "inchi", "inchikey", "cas", "name"]


# ------------------------------------------------------------
# Helper: does value look like SMILES?
# ------------------------------------------------------------

def _looks_like_smiles_value(val: str) -> bool:
    if not isinstance(val, str):
        return False
    if " " in val:
        return False
    try:
        mol = Chem.MolFromSmiles(val)
        return mol is not None
    except Exception:
        return False


# ------------------------------------------------------------
# Helper: does value look like CAS?
# ------------------------------------------------------------

def _looks_like_cas(val: str) -> bool:
    if not isinstance(val, str):
        return False
    return normalize_cas(val) is not None


# ------------------------------------------------------------
# Identify candidate identifier columns
# ------------------------------------------------------------

def get_candidate_identifier_columns(df: pd.DataFrame) -> Dict[str, List[str]]:
    """
    Detects which DataFrame columns may contain identifiers using:
    - Column name matching (Option B)
    - Pattern recognition (Option B)
    """
    candidates = {k: [] for k in PRIORITY_ORDER}

    # --- Pass 1: column name matching ---
    for col in df.columns:
        col_lower = col.lower().strip()

        for idtype, patterns in COLNAME_PATTERNS.items():
            if any(p in col_lower for p in patterns):
                if col not in candidates[idtype]:
                    candidates[idtype].append(col)

    # --- Pass 2: content-based inference ---
    for col in df.columns:
        values = df[col].dropna().astype(str)

        # Try identify SMILES
        if col not in sum(candidates.values(), []):
            if any(_looks_like_smiles_value(v) for v in values.head(50)):
                candidates["smiles"].append(col)
                continue

        # Try identify InChI
        if col not in sum(candidates.values(), []):
            if any(v.startswith("InChI=") for v in values.head(50)):
                candidates["inchi"].append(col)
                continue

        # Try CAS
        if col not in sum(candidates.values(), []):
            if any(_looks_like_cas(v) for v in values.head(50)):
                candidates["cas"].append(col)
                continue

    # Ensure we always have at least one fallback name column
    if not candidates["name"]:
        candidates["name"].append(df.columns[0])

    return candidates


# ------------------------------------------------------------
# Pick best identifier for a single row
# ------------------------------------------------------------

def pick_best_identifier(row, candidates: Dict[str, List[str]]) -> Dict[str, Any]:
    """
    For a single row, choose the best identifier according to:
        Priority B + strict validation
    """
    warnings = []

    for idtype in PRIORITY_ORDER:
        for col in candidates.get(idtype, []):
            raw = row.get(col)
            if raw is None:
                continue

            raw_str = str(raw).strip()
            if raw_str == "":
                continue

            # --- Strict validation rules ---
            if idtype == "smiles":
                if _looks_like_smiles_value(raw_str):
                    return {"identifier_value": raw_str, "identifier_type": "smiles", "warnings": warnings}

            elif idtype == "inchi":
                if raw_str.startswith("InChI="):
                    try:
                        mol = Chem.MolFromInchi(raw_str)
                        if mol is not None:
                            return {"identifier_value": raw_str, "identifier_type": "inchi", "warnings": warnings}
                    except Exception:
                        continue

            elif idtype == "inchikey":
                # Accept if it matches known pattern via detect_identifier_type
                if detect_identifier_type(raw_str) == "inchikey":
                    return {"identifier_value": raw_str.upper(), "identifier_type": "inchikey", "warnings": warnings}

            elif idtype == "cas":
                normalized = normalize_cas(raw_str)
                if normalized:
                    return {"identifier_value": normalized, "identifier_type": "cas", "warnings": warnings}

            elif idtype == "name":
                return {"identifier_value": raw_str, "identifier_type": "name", "warnings": warnings}

    warnings.append("No usable identifier found.")
    return {"identifier_value": None, "identifier_type": None, "warnings": warnings}


# ------------------------------------------------------------
# Build final fields
# ------------------------------------------------------------

def build_final_fields(flat: Dict[str, Any]) -> Dict[str, Any]:
    """
    final = experimental if exists else computed
    source updated accordingly
    """

    PROPS = [
        "boiling_point_c",
        "melting_point_c",
        "flash_point_c",
        "autoignition_temp_c",
        "vapor_pressure_pa",
        "water_solubility_mg_l",
        "refractive_index",
        "density_g_ml",
        "logp",
        "heat_of_vaporization_kj_mol",
        "critical_temp_c",
        "critical_pressure_bar",
        "mw",
        "exact_mass",
        "clogp",
        "tpsa",
        "hbd",
        "hba",
        "rot_bonds",
        "ring_count",
        "fraction_csp3",
        "molar_refractivity",
        "smiles",
        "inchi",
        "inchikey"
    ]

    for prop in PROPS:
        exp_val = flat.get(f"experimental_{prop}")
        comp_val = flat.get(f"computed_{prop}")
        src_key = f"source_{prop}"

        if exp_val is not None:
            flat[f"final_{prop}"] = exp_val
            flat[src_key] = "pubchem"
        elif comp_val is not None:
            flat[f"final_{prop}"] = comp_val
            if flat.get(src_key) is None:
                flat[src_key] = "computed"
        else:
            flat[f"final_{prop}"] = None
            flat[src_key] = None

    return flat


# ------------------------------------------------------------
# Resolve a single identifier value
# ------------------------------------------------------------

def resolve_identifier(value: str, id_type: str) -> Dict[str, Any]:
    """
    Normalize → RDKit → PubChem → fallback → merge.
    """

    if value is None or str(value).strip() == "":
        return {"warnings": ["Empty identifier"], "timestamp": datetime.datetime.utcnow().isoformat()}

    cleaned = clean_whitespace(value)
    normalized = normalize_identifier(cleaned, id_type)

    flat = {
        "input": value,
        "normalized_input": normalized,
        "identifier_type": id_type,
        "warnings": []
    }

    # --- RDKit ---
    rd = compute_rdkit_descriptors(normalized, id_type)
    for k, v in rd.items():
        flat[k] = v
    flat["warnings"].extend(rd.get("warnings", []))

    # --- PubChem ---
    pub = get_pubchem_properties(normalized, id_type)
    for k, v in pub.items():
        if k == "warnings":
            flat["warnings"].extend(v)
        else:
            flat[k] = v

    # --- Fallbacks ---
    flat = apply_fallbacks(flat)

    # --- Merge final fields ---
    flat = build_final_fields(flat)

    flat["timestamp"] = datetime.datetime.utcnow().isoformat()
    return flat


# ------------------------------------------------------------
# Resolve full DataFrame
# ------------------------------------------------------------

def resolve_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Apply per-row identifier picking and full pipeline."""
    candidates = get_candidate_identifier_columns(df)
    results = []

    for _, row in df.iterrows():
        selection = pick_best_identifier(row, candidates)
        val = selection["identifier_value"]
        id_type = selection["identifier_type"]
        w = selection["warnings"]

        if val is None:
            results.append({
                "input": None,
                "warnings": w,
                "timestamp": datetime.datetime.utcnow().isoformat()
            })
            continue

        rec = resolve_identifier(val, id_type)
        rec["warnings"].extend(w)
        results.append(rec)

    # identifier_col unused but required by Option 1 signature
    return integrate_results_into_dataframe(df, results, identifier_col=None)


# ------------------------------------------------------------
# CLI interface
# ------------------------------------------------------------

def cli():
    parser = argparse.ArgumentParser(description="Physical Properties Retrieval App")
    parser.add_argument("input_excel", help="Path to input Excel file")
    parser.add_argument("output_excel", help="Path to save output Excel file")
    parser.add_argument("--sheet", default=None)
    parser.add_argument("--log", default="INFO")

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    df = load_excel(args.input_excel, sheet_name=args.sheet)
    out = resolve_dataframe(df)
    save_excel(out, args.output_excel)


if __name__ == "__main__":
    cli()