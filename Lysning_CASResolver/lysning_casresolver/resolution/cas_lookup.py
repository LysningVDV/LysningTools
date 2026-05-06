import logging
from datetime import datetime

from ..util.validate import normalize_cas, validate_cas, classify_mixture
from ..util.cache import get_cached, set_cached

from .pubchem_lookup import resolve_pubchem_cas
from .chemspider_lookup import resolve_chemspider_cas
from .cactus_lookup import resolve_cactus_cas
from .opsin_lookup import resolve_opsin_cas
from .rdkit_convert import rdkit_complete_from_smiles_or_inchi

logger = logging.getLogger(__name__)


def resolve_cas(raw_value: str) -> dict:
    """
    Ordered CAS → structure pipeline:

        PubChem → ChemSpider → Cactus → OPSIN → RDKit fallback

    This version is fully indentation‑safe and ChemSpider‑aware
    (emits a log hook CHEMSPIDER_USED).
    """

    original = raw_value
    warnings = []
    timestamp = datetime.utcnow().isoformat() + "Z"

    # -----------------------------------------------------
    # 1) Normalize CAS
    # -----------------------------------------------------
    try:
        normalized, w = normalize_cas(raw_value)
        if w:
            warnings.append(w)
        cas = normalized
    except Exception as exc:
        # Cannot normalize CAS at all
        return {
            "input": original,
            "cas": "",
            "smiles": "",
            "inchi": "",
            "inchikey": "",
            "mw": "",
            "source": "invalid",
            "warning": f"CAS normalization failed: {exc}",
            "mixture_type": "unknown",
            "timestamp": timestamp
        }

    # Strict checksum validation
    try:
        cas = validate_cas(cas)
    except Exception as exc:
        warnings.append(f"checksum failed: {exc}")

    mixture_type = classify_mixture(cas)

    # -----------------------------------------------------
    # 2) Check cache
    # -----------------------------------------------------
    cached = get_cached(cas)
    if cached:
        logger.debug("Cache hit for CAS %s", cas)
        return cached

    # -----------------------------------------------------
    # 3) PubChem
    # -----------------------------------------------------
    try:
        result = resolve_pubchem_cas(cas)
        if result:
            warnings.extend(result.get("warning_list", []))
            final = _finalize_result(original, cas, result, "pubchem", warnings, mixture_type)
            set_cached(cas, final)
            return final
        warnings.append("PubChem: no result")
    except Exception as exc:
        logger.debug("PubChem lookup failed for %s: %s", cas, exc)
        warnings.append(f"PubChem error: {exc}")

    # -----------------------------------------------------
    # 4) ChemSpider (with usage hook)
    # -----------------------------------------------------
    try:
        logger.info("CHEMSPIDER_USED")  # <-- ChemSpider usage counter hook
        result = resolve_chemspider_cas(cas)
        if result:
            warnings.extend(result.get("warning_list", []))
            final = _finalize_result(original, cas, result, "chemspider", warnings, mixture_type)
            set_cached(cas, final)
            return final
        warnings.append("ChemSpider: no result")
    except Exception as exc:
        logger.debug("ChemSpider lookup failed for %s: %s", cas, exc)
        warnings.append(f"ChemSpider error: {exc}")

    # -----------------------------------------------------
    # 5) Cactus
    # -----------------------------------------------------
    try:
        result = resolve_cactus_cas(cas)
        if result:
            warnings.extend(result.get("warning_list", []))
            final = _finalize_result(original, cas, result, "cactus", warnings, mixture_type)
            set_cached(cas, final)
            return final
        warnings.append("Cactus: no result")
    except Exception as exc:
        logger.debug("Cactus lookup failed for %s: %s", cas, exc)
        warnings.append(f"Cactus error: {exc}")

    # -----------------------------------------------------
    # 6) OPSIN
    # -----------------------------------------------------
    try:
        result = resolve_opsin_cas(cas)
        if result:
            warnings.extend(result.get("warning_list", []))
            final = _finalize_result(original, cas, result, "opsin", warnings, mixture_type)
            set_cached(cas, final)
            return final
        warnings.append("OPSIN: no result")
    except Exception as exc:
        logger.debug("OPSIN lookup failed for %s: %s", cas, exc)
        warnings.append(f"OPSIN error: {exc}")

    # -----------------------------------------------------
    # 7) RDKit fallback
    # -----------------------------------------------------
    try:
        rdkit_result = rdkit_complete_from_smiles_or_inchi(None, None)
        if rdkit_result:
            warnings.append("RDKit fallback used")
            final = _finalize_result(original, cas, rdkit_result, "rdkit", warnings, mixture_type)
            set_cached(cas, final)
            return final
    except Exception as exc:
        logger.debug("RDKit fallback failed for %s: %s", cas, exc)
        warnings.append(f"RDKit error: {exc}")

    # -----------------------------------------------------
    # 8) Total Failure
    # -----------------------------------------------------
    warning_str = "; ".join(warnings)

    final = {
        "input": original,
        "cas": cas,
        "smiles": "",
        "inchi": "",
        "inchikey": "",
        "mw": "",
        "source": "unresolved",
        "warning": warning_str,
        "mixture_type": mixture_type,
        "timestamp": timestamp
    }

    set_cached(cas, final)
    return final


# ---------------------------------------------------------------------
# HELPER: finalize resolver result
# ---------------------------------------------------------------------

def _finalize_result(original, cas, resolver_result, source, warnings, mixture_type):
    timestamp = resolver_result.get("timestamp") or datetime.utcnow().isoformat() + "Z"

    smiles = resolver_result.get("smiles")
    inchi = resolver_result.get("inchi")

    rdkit_data = rdkit_complete_from_smiles_or_inchi(smiles, inchi)

    return {
        "input": original,
        "cas": cas,
        "smiles": rdkit_data.get("smiles", ""),
        "inchi": rdkit_data.get("inchi", ""),
        "inchikey": rdkit_data.get("inchikey", ""),
        "mw": rdkit_data.get("mw", ""),
        "source": source,
        "warning": "; ".join(warnings),
        "mixture_type": mixture_type,
        "timestamp": timestamp
    }