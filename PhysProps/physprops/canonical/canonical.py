from .mapper import build_canonical_row
from __future__ import annotations

from typing import Dict, Any, Tuple, List
import pandas as pd
import numpy as np


# ---------- helpers (deterministic) ----------

def _is_blank(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and np.isnan(v):
        return True
    if isinstance(v, str) and v.strip() == "":
        return True
    return False


def _to_datetime_safe(x) -> pd.Timestamp:
    """Parse timestamps deterministically; unparseable -> NaT."""
    if _is_blank(x):
        return pd.NaT
    try:
        return pd.to_datetime(x, errors="coerce")
    except Exception:
        return pd.NaT


def _source_weight(src: Any) -> int:
    """Deterministic precedence weight for source tags."""
    if _is_blank(src):
        return 0
    s = str(src).strip().lower()
    if s == "pubchem":
        return 3
    if s == "fallback":
        return 2
    if s == "computed":
        return 1
    return 0


def _pick_logp_source_column(row_dict: Dict[str, Any]) -> str | None:
    """
    Deterministically mirror build_canonical_row's logP preference:
    - if final_logp exists => source_logp
    - else if final_clogp exists => source_clogp
    - else None
    """
    if not _is_blank(row_dict.get("final_logp")):
        return "source_logp"
    if not _is_blank(row_dict.get("final_clogp")):
        return "source_clogp"
    return None


def _pubchem_coverage_score(row_dict: Dict[str, Any]) -> Tuple[int, int]:
    """
    Returns:
      (score_sum, pubchem_count)

    score_sum uses weights: pubchem=3, fallback=2, computed=1, else 0
    pubchem_count counts how many of the tracked sources are exactly pubchem.
    """
    source_cols = [
        "source_mw",
        "source_tpsa",
        "source_boiling_point_c",
        "source_vapor_pressure_pa",
        "source_density_g_ml",
        "source_water_solubility_mg_l",
    ]

    logp_source_col = _pick_logp_source_column(row_dict)
    if logp_source_col:
        source_cols.append(logp_source_col)

    score_sum = 0
    pubchem_count = 0

    for col in source_cols:
        src = row_dict.get(col)
        w = _source_weight(src)
        score_sum += w
        if not _is_blank(src) and str(src).strip().lower() == "pubchem":
            pubchem_count += 1

    return score_sum, pubchem_count


# ---------- main function ----------

def build_canonical_dataframe(df_wide: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Build canonical physprops DataFrame from wide pipeline output.

    Dedupe rule (as requested):
      1) PubChem coverage wins (source precedence scoring across key properties)
      2) then latest timestamp
      3) stable tie-break: lowest input row index

    Returns:
      canonical_df: one row per inchi_key (canonical schema columns only)
      audit_df: Excel-friendly log of winners/losers with ranking metrics
    """
    canonical_rows: List[Dict[str, Any]] = []
    audit_rows: List[Dict[str, Any]] = []

    # 1) Map each wide row -> canonical dict (using your deterministic builder)
    for i, r in df_wide.iterrows():
        wide = r.to_dict()

        canon = build_canonical_row(wide)  # <-- your mapping function

        if not canon or _is_blank(canon.get("inchi_key")):
            audit_rows.append({
                "inchi_key": None,
                "input_row_index": int(i),
                "selected": False,
                "reason": "missing_inchi_key",
                "timestamp_raw": wide.get("timestamp"),
            })
            continue

        # Ranking metrics (computed from the WIDE row sources + canonical timestamp)
        score_sum, pubchem_count = _pubchem_coverage_score(wide)
        ts = _to_datetime_safe(canon.get("timestamp_updated"))

        # Store internal rank fields for deterministic selection
        canon["_input_row_index"] = int(i)
        canon["_rank_score_sum"] = int(score_sum)
        canon["_rank_pubchem_count"] = int(pubchem_count)
        canon["_rank_timestamp"] = ts

        canonical_rows.append(canon)

    if not canonical_rows:
        return pd.DataFrame(), pd.DataFrame(audit_rows)

    df_c = pd.DataFrame(canonical_rows)

    # 2) Deterministic sorting:
    #    - inchi_key ascending
    #    - pubchem_count descending (more pubchem-backed properties wins)
    #    - score_sum descending (overall precedence score wins)
    #    - timestamp descending (latest wins), NaT last
    #    - input_row_index ascending (stable tie-break)
    df_c["_ts_is_nat"] = df_c["_rank_timestamp"].isna()

    df_sorted = df_c.sort_values(
        by=["inchi_key", "_rank_pubchem_count", "_rank_score_sum", "_ts_is_nat", "_rank_timestamp", "_input_row_index"],
        ascending=[True, False, False, True, False, True],
        kind="mergesort",  # stable
    )

    # 3) Winner per inchi_key = first row after sorting
    winners = df_sorted.groupby("inchi_key", sort=True).head(1).copy()
    winners["_selected"] = True

    # 4) Losers for audit
    winners_idx = winners[["inchi_key", "_input_row_index"]].rename(
        columns={"_input_row_index": "_winner_input_row_index"}
    )
    df_join = df_sorted.merge(winners_idx, on="inchi_key", how="left")
    df_join["_selected"] = df_join["_input_row_index"] == df_join["_winner_input_row_index"]
    losers = df_join[~df_join["_selected"]].copy()

    # 5) Build audit (Excel-friendly)
    for _, w in winners.iterrows():
        audit_rows.append({
            "inchi_key": w["inchi_key"],
            "input_row_index": int(w["_input_row_index"]),
            "selected": True,
            "rank_pubchem_count": int(w["_rank_pubchem_count"]),
            "rank_score_sum": int(w["_rank_score_sum"]),
            "rank_timestamp": None if pd.isna(w["_rank_timestamp"]) else str(w["_rank_timestamp"]),
            "source_primary": w.get("source_primary"),
            "source_secondary": w.get("source_secondary"),
            "needs_review": w.get("needs_review"),
            "warnings": w.get("warnings"),
            "reason": "winner",
        })

    for _, l in losers.iterrows():
        audit_rows.append({
            "inchi_key": l["inchi_key"],
            "input_row_index": int(l["_input_row_index"]),
            "selected": False,
            "rank_pubchem_count": int(l["_rank_pubchem_count"]),
            "rank_score_sum": int(l["_rank_score_sum"]),
            "rank_timestamp": None if pd.isna(l["_rank_timestamp"]) else str(l["_rank_timestamp"]),
            "source_primary": l.get("source_primary"),
            "source_secondary": l.get("source_secondary"),
            "needs_review": l.get("needs_review"),
            "warnings": l.get("warnings"),
            "winner_input_row_index": int(l["_winner_input_row_index"]) if not _is_blank(l["_winner_input_row_index"]) else None,
            "reason": "deduped_out",
        })

    audit_df = pd.DataFrame(audit_rows)

    # 6) Drop internal rank columns from canonical output
    internal_cols = [c for c in winners.columns if c.startswith("_rank_") or c.startswith("_") or c in ("_ts_is_nat",)]
    canonical_df = winners.drop(columns=internal_cols, errors="ignore")

    return canonical_df, audit_df