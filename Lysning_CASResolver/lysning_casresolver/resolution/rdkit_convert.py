import logging
from rdkit import Chem
from rdkit.Chem import Descriptors

logger = logging.getLogger(__name__)

def sanitize_smiles(s: str) -> str:
    """
    Remove non-SMILES extensions that some sources append (e.g. CXSMILES-like '|...|').
    Keeps only the part before the first '|'.
    """
    s = (s or "").strip()
    if "|" in s:
        s = s.split("|", 1)[0].strip()
    return s

def rdkit_complete_from_smiles_or_inchi(smiles: str | None,
                                        inchi: str | None) -> dict:
    """
    Complete structural metadata using RDKit.

    Ensures a consistent set of:
        - smiles
        - inchi
        - inchikey
        - mw  (RDKit-calculated molecular weight)

    The orchestrator calls this to:
        - canonicalize structures from external resolvers
        - fill missing InChIKey
        - compute MW

    Parameters
    ----------
    smiles : str | None
    inchi : str | None

    Returns
    -------
    dict
        {
            "smiles": "...",
            "inchi": "...",
            "inchikey": "...",
            "mw": float
        }
        On failure, values may be "" or None safely.
    """
    # Start with supplied values
    current_smiles = smiles or ""
    current_inchi = inchi or ""

    # Try to build a molecule from smiles or inchi
    mol = None

    # Preserve originals for audit/debug
    orig_smiles = current_smiles
    orig_inchi = current_inchi

    def sanitize_smiles(s: str) -> str:
        """
        Remove non-SMILES extensions appended by some sources (e.g. CXSMILES-like '|...|').
        Keep only the part before the first '|'.
        """
        s = (s or "").strip()
        if "|" in s:
            s = s.split("|", 1)[0].strip()
        return s

    def sanitize_inchi(s: str) -> str:
        """
        Light cleanup for InChI strings.
        Do NOT attempt to "repair" chemistry; only trim and remove common hidden chars.
        """
        s = (s or "").strip()
        if s:
            s = s.replace("\ufeff", "").replace("\u00A0", " ").strip()
        return s

    rdkit_error = ""

    # First: try SMILES if provided
    if current_smiles:
        try:
            current_smiles = sanitize_smiles(current_smiles)
            mol = Chem.MolFromSmiles(current_smiles)
            if mol is None:
                rdkit_error = "smiles_parse_failed"
                logger.debug("RDKit failed to parse SMILES '%s'.", current_smiles)
        except Exception as exc:
            rdkit_error = f"smiles_exception:{exc}"
            logger.debug("RDKit crashed on SMILES '%s': %s", current_smiles, exc)
            mol = None

    # Second: try InChI if SMILES parsing failed
    if mol is None:
        inchi = sanitize_inchi(current_inchi)

        # Guard: only attempt RDKit InChI parsing for real InChI strings
        if inchi.startswith("InChI="):
            try:
                mol = Chem.MolFromInchi(inchi)
                if mol is None:
                    rdkit_error = rdkit_error or "inchi_parse_failed"
                    logger.debug("RDKit failed to parse InChI '%s'.", inchi)
            except Exception as exc:
                rdkit_error = rdkit_error or f"inchi_exception:{exc}"
                logger.debug("RDKit crashed on InChI '%s': %s", inchi, exc)
                mol = None
        else:
            # likely InChIKey or non-InChI identifier; skip quietly
            rdkit_error = rdkit_error or "inchi_not_attempted_not_inchi"

    # At this point, if mol is still None, we cannot enrich anything
    if mol is None:
        return {
            # return original values for traceability
            "smiles": (orig_smiles or ""),
            "inchi": (orig_inchi or ""),
            "inchikey": "",
            "mw": None,
            "rdkit_error": rdkit_error,
        }

    # Now canonicalize & fill missing fields
    # 1. Canonical SMILES
    try:
        current_smiles = Chem.MolToSmiles(mol, canonical=True)
    except Exception as exc:
        logger.debug("RDKit failed to generate canonical SMILES: %s", exc)
        # keep best-known value
        current_smiles = (current_smiles or "")

    # 2. InChI
    try:
        current_inchi = Chem.MolToInchi(mol)
    except Exception as exc:
        logger.debug("RDKit failed to generate InChI: %s", exc)
        current_inchi = (current_inchi or "")

    # 3. InChIKey (only if InChI looks valid)
    inchikey = ""
    try:
        if current_inchi and str(current_inchi).startswith("InChI="):
            inchikey = Chem.InchiToInchiKey(current_inchi)
    except Exception as exc:
        logger.debug("RDKit failed to generate InChIKey: %s", exc)
        inchikey = ""

    # 4. MW
    mw = None
    try:
        mw = float(Descriptors.MolWt(mol))
    except Exception as exc:
        logger.debug("RDKit failed to compute MW: %s", exc)
        mw = None

    return {
        "smiles": current_smiles or "",
        "inchi": current_inchi or "",
        "inchikey": inchikey or "",
        "mw": mw,
        "rdkit_error": rdkit_error,
    }