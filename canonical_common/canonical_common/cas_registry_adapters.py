# canonical_common/cas_registry_adapters.py
import pandas as pd
from canonical_common.cas_registry import DEFAULT_DB2_COLUMNS, _utc_now_iso

def incoming_from_structurer(df_struct: pd.DataFrame) -> pd.DataFrame:
    """
    Expected CAS_Structurer columns (example):
      - cas_input
      - cas_number_normalized
      - cas_status
      - evidence
    """
    out = pd.DataFrame({
        "cas_input": df_struct.get("cas_input", ""),
        "cas_number_normalized": df_struct.get("cas_number_normalized", ""),
        "cas_status": df_struct.get("cas_status", ""),
        "inchi_key": "",
        "inchi": "",
        "smiles": "",
        "resolver_source": "CAS_Structurer",
        "resolver_confidence": pd.NA,
        "resolution_timestamp_utc": _utc_now_iso(),
        "evidence": df_struct.get("evidence", ""),
        "notes": "",
    })
    return out


import pandas as pd
from canonical_common.cas_registry import _utc_now_iso  # if you already had this helper; else inline Timestamp.now

def _col(df: pd.DataFrame, *names: str, default=""):
    """Return the first existing column among names, else a scalar default."""
    for n in names:
        if n in df.columns:
            return df[n]
    return default

def incoming_from_resolver(df_res: pd.DataFrame) -> pd.DataFrame:
    """
    Accepts resolver outputs that use either canonical names or resolver-native names.
    Resolver-native (from your main.py): cas, inchikey, source, warning, cas_validity, timestamp, mixture_type. [1](https://lysninginnovationconsultant-my.sharepoint.com/personal/villeneuve_lysning_nl/Documents/Microsoft%20Copilot%20Chat%20Files/main.py)
    """

    # CAS normalized column (your resolver uses 'cas')
    cas_norm = _col(df_res, "cas_number_normalized", "cas", "cas_normalized", default="")

    # InChIKey column (your resolver uses 'inchikey')
    ik = _col(df_res, "inchi_key", "inchikey", "InChIKey", default="")

    # InChI / SMILES
    inchi = _col(df_res, "inchi", "InChI", default="")
    smiles = _col(df_res, "smiles", "SMILES", default="")

    # Source/provenance (your resolver uses 'source')
    src = _col(df_res, "resolver_source", "source", default="Lysning_CASResolver")

    # Confidence often absent in current resolver outputs; keep NA if missing
    conf = _col(df_res, "resolver_confidence", "confidence", default=pd.NA)

    # Timestamp (your resolver uses 'timestamp')
    ts = _col(df_res, "resolution_timestamp_utc", "timestamp", default=_utc_now_iso())

    # Evidence / notes (your resolver uses 'warning')
    evidence = _col(df_res, "evidence", "warning", default="")
    notes = _col(df_res, "notes", default="")

    # Status: use resolver-native 'cas_validity' if present, else derive
    # Typical: valid / invalid / repaired; mixtures/UVCB handled below
    # status source
    status = _col(df_res, "cas_status", "cas_validity", default="valid")
    status = pd.Series(status).astype(str).str.lower().str.strip()

    mixture_type = _col(df_res, "mixture_type", default="")

    # Base status (keep resolver's own validity/status if present)
    status = _col(df_res, "cas_status", "cas_validity", default="valid")
    status = pd.Series(status).astype(str).str.lower().str.strip()

    # Explicit mapping from mixture_type -> governance cas_status
    if isinstance(mixture_type, pd.Series):
        mt = mixture_type.astype(str).str.lower().str.strip()

        is_uvcb = mt.eq("natural product / uvcb")
        is_mix = mt.isin({
            "fragrance mixture",
            "polymer / complex mixture",
            "mixture (multi-component structure)",
        })

        # Only override when explicitly mixture/uvcb
        status = status.where(~is_mix, "mixture")
        status = status.where(~is_uvcb, "uvcb")

    out = pd.DataFrame({
        "cas_input": _col(df_res, "cas_input", "input", default=""),
        "cas_number_normalized": _col(df_res, "cas_number_normalized", "cas", "cas_normalized", default=""),
        "cas_status": status,
        "mixture_type": mixture_type,
        "inchi_key": _col(df_res, "inchi_key", "inchikey", "InChIKey", default=""),
        "inchi": _col(df_res, "inchi", "InChI", default=""),
        "smiles": _col(df_res, "smiles", "SMILES", default=""),
        "resolver_source": _col(df_res, "resolver_source", "source", default="Lysning_CASResolver"),
        "resolver_confidence": _col(df_res, "resolver_confidence", "confidence", default=pd.NA),
        "resolution_timestamp_utc": _col(df_res, "resolution_timestamp_utc", "timestamp", default=_utc_now_iso()),
        "evidence": _col(df_res, "evidence", "warning", default=""),
        "notes": _col(df_res, "notes", default=""),
    })

    return out

    return out