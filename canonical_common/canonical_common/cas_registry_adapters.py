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


def incoming_from_resolver(df_res: pd.DataFrame) -> pd.DataFrame:
    """
    Expected Lysning_CASResolver columns (example):
      - cas_number_normalized
      - inchi_key
      - inchi
      - smiles
      - resolver_source
      - resolver_confidence
      - resolution_timestamp_utc (optional)
      - notes/evidence (optional)
    """
    out = pd.DataFrame({
        "cas_input": df_res.get("cas_input", ""),
        "cas_number_normalized": df_res.get("cas_number_normalized", ""),
        "cas_status": df_res.get("cas_status", "valid"),
        "inchi_key": df_res.get("inchi_key", ""),
        "inchi": df_res.get("inchi", ""),
        "smiles": df_res.get("smiles", ""),
        "resolver_source": df_res.get("resolver_source", "Lysning_CASResolver"),
        "resolver_confidence": df_res.get("resolver_confidence", pd.NA),
        "resolution_timestamp_utc": df_res.get("resolution_timestamp_utc", _utc_now_iso()),
        "evidence": df_res.get("evidence", ""),
        "notes": df_res.get("notes", ""),
    })
    return out