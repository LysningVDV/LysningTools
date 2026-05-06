import logging
from rdkit import Chem
from rdkit.Chem import Descriptors

logger = logging.getLogger(__name__)


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

    # Try to build a molecule from smile or inchi
    mol = None

    # First: try SMILES if provided
    if current_smiles:
        try:
            mol = Chem.MolFromSmiles(current_smiles)
            if mol is None:
                logger.debug("RDKit failed to parse SMILES '%s'.", current_smiles)
        except Exception as exc:
            logger.debug("RDKit crashed on SMILES '%s': %s", current_smiles, exc)
            mol = None

    # Second: try InChI if SMILES parsing failed
    if mol is None and current_inchi:
        try:
            mol = Chem.MolFromInchi(current_inchi)
            if mol is None:
                logger.debug("RDKit failed to parse InChI '%s'.", current_inchi)
        except Exception as exc:
            logger.debug("RDKit crashed on InChI '%s': %s", current_inchi, exc)
            mol = None

    # At this point, if mol is still None, we cannot enrich anything
    if mol is None:
        return {
            "smiles": current_smiles,
            "inchi": current_inchi,
            "inchikey": "",
            "mw": None
        }

    # Now canonicalize & fill missing fields
    # 1. Canonical SMILES
    try:
        current_smiles = Chem.MolToSmiles(mol)
    except Exception as exc:
        logger.debug("RDKit failed to generate canonical SMILES: %s", exc)

    # 2. InChI
    try:
        current_inchi = Chem.MolToInchi(mol)
    except Exception as exc:
        logger.debug("RDKit failed to generate InChI: %s", exc)

    # 3. InChIKey
    try:
        inchikey = Chem.InchiToInchiKey(current_inchi) if current_inchi else ""
    except Exception as exc:
        logger.debug("RDKit failed to generate InChIKey: %s", exc)
        inchikey = ""

    # 4. MW
    try:
        mw = float(Descriptors.MolWt(mol))
    except Exception as exc:
        logger.debug("RDKit failed to compute MW: %s", exc)
        mw = None

    return {
        "smiles": current_smiles or "",
        "inchi": current_inchi or "",
        "inchikey": inchikey or "",
        "mw": mw
    }