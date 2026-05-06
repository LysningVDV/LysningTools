# physprops/canonical/builder.py
from __future__ import annotations

from typing import Any, Dict, List, Tuple
import pandas as pd
import numpy as np

from .mapper import build_canonical_row


# === Frozen canonical column order (schema v1.0) ===
CANONICAL_ORDER = [
    "inchi_key",
    "cas_number",
    "smiles",
    "name_preferred",
    "molecular_weight_g_mol",
    "logP_octanol_water",
    "topological_polar_surface_area_A2",
    "num_heavy_atoms",
    "vapor_pressure_Pa_25C",
    "log_vapor_pressure_Pa_25C",
    "henry_constant_mol_m3_Pa_25C",
    "log_henry_constant_mol_m3_Pa_25C",
    "source_henry_constant",
    "boiling_point_C",
    "melting_point_C",
    "water_solubility_mg_L_25C",
    "log_water_solubility_mg_L_25C",
    "density_g_mL_25C",
    "experimental_hsp_delta_d_mpa05",
    "experimental_hsp_delta_p_mpa05",
    "experimental_hsp_delta_h_mpa05",
    "source_hsp",
    "computed_hsp_delta_d_mpa05",
    "computed_hsp_delta_p_mpa05",
    "computed_hsp_delta_h_mpa05",
    "source_hsp_computed",
    "physical_state_25C",
    "is_volatile",
    "needs_review",
    "source_primary",
    "source_secondary",
    "confidence_score",
    "warnings",
    "timestamp_updated",
]


# === helpers ===

def _is_blank(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and np.isnan(v):
        return True
    if isinstance(v, str) and v.strip() == "":
        return True
    return False


def _to_datetime_safe(x: Any) -> pd.Timestamp:
    if _is_blank(x):
        return pd.NaT
    try:
        return pd.to_datetime(x, errors="coerce")
    except Exception:
        return pd.NaT


def _source_weight(src: Any) -> int:
    """
    Deterministic precedence weights for coverage scoring.
    """
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


def _pick_logp_source_column(wide_row: Dict[str, Any]) -> str | None:
    """
    Must mirror mapper logic exactly.
    """
    if not _is_blank(wide_row.get("final_logp")):
        return "source_logp"
    if not _is_blank(wide_row.get("final_clogp")):
        return "source_clogp"
    return None


def _pubchem_coverage_score(wide_row: Dict[str, Any]) -> Tuple[int, int]:
    """
    Compute PubChem coverage score using explicit source_* fields only.

    Returns:
      score_sum      : weighted sum (pubchem=3, fallback=2, computed=1)
      pubchem_count  : number of fields backed by pubchem
    """
    source_cols = [
        "source_mw",
        "source_tpsa",
        "source_boiling_point_c",
        "source_vapor_pressure_pa",
        "source_density_g_ml",
        "source_water_solubility_mg_l",
    ]

    lp_col = _pick_logp_source_column(wide_row)
    if lp_col:
        source_cols.append(lp_col)

    score_sum = 0
    pubchem_count = 0

    for col in source_cols:
        src = wide_row.get(col)
        w = _source_weight(src)
        score_sum += w
        if not _is_blank(src) and str(src).strip().lower() == "pubchem":
            pubchem_count += 1

    return score_sum, pubchem_count


# ------------------------------------------------------------
# canonical builder
# ------------------------------------------------------------

def build_canonical_dataframe(
    df_wide: pd.DataFrame,
    *,
    strict_schema: bool = True,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Build canonical physprops DataFrame and deduplication audit log.

    Deduplication rule (frozen):
      1) PubChem coverage wins (per-property source precedence scoring)
      2) then latest timestamp_updated
      3) stable tie-break: lowest input row index

    Returns:
      canonical_df : one row per inchi_key, ordered exactly as CANONICAL_ORDER
      audit_df     : Excel-friendly audit log (winners + losers)
    """

    canonical_rows: List[Dict[str, Any]] = []
    audit_rows: List[Dict[str, Any]] = []

    # --- Step 1: map wide rows -> canonical rows ---
    for i, r in df_wide.iterrows():
        wide = r.to_dict()

        canon = build_canonical_row(wide)
        if not canon or _is_blank(canon.get("inchi_key")):
            audit_rows.append({
                "inchi_key": None,
                "input_row_index": int(i),
                "selected": False,
                "reason": "missing_inchi_key",
                "timestamp_raw": wide.get("timestamp"),
            })
            continue

        score_sum, pubchem_count = _pubchem_coverage_score(wide)
        ts = _to_datetime_safe(canon.get("timestamp_updated"))

        canon["_input_row_index"] = int(i)
        canon["_rank_score_sum"] = int(score_sum)
        canon["_rank_pubchem_count"] = int(pubchem_count)
        canon["_rank_timestamp"] = ts
        canon["_ts_is_nat"] = pd.isna(ts)

        canonical_rows.append(canon)

    if not canonical_rows:
        canonical_df = pd.DataFrame(columns=CANONICAL_ORDER)
        audit_df = pd.DataFrame(audit_rows)
        return canonical_df, audit_df

    df_c = pd.DataFrame(canonical_rows)

    # --- Step 2: deterministic sort for winner selection ---
    df_sorted = df_c.sort_values(
        by=[
            "inchi_key",
            "_rank_pubchem_count",
            "_rank_score_sum",
            "_ts_is_nat",
            "_rank_timestamp",
            "_input_row_index",
        ],
        ascending=[True, False, False, True, False, True],
        kind="mergesort",  # stable
    )

    winners = df_sorted.groupby("inchi_key", sort=True).head(1).copy()
    winners["_selected"] = True

    # --- Step 3: identify losers for audit ---
    winners_idx = winners[["inchi_key", "_input_row_index"]].rename(
        columns={"_input_row_index": "_winner_input_row_index"}
    )

    df_join = df_sorted.merge(winners_idx, on="inchi_key", how="left")
    df_join["_selected"] = df_join["_input_row_index"] == df_join["_winner_input_row_index"]
    losers = df_join[~df_join["_selected"]].copy()

    # --- Step 4: build canonical_df and audit_df ---
    canonical_df = winners.copy()

    # Enforce column order; optionally strict schema
    if strict_schema:
        for col in CANONICAL_ORDER:
            if col not in canonical_df.columns:
                canonical_df[col] = None
        canonical_df = canonical_df.reindex(columns=CANONICAL_ORDER)
    else:
        # If not strict, still put canonical cols first, keep extras at end.
        extras = [c for c in canonical_df.columns if c not in CANONICAL_ORDER]
        canonical_df = canonical_df.reindex(columns=CANONICAL_ORDER + extras)

    # --- Build audit log ---
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
            "reason": "loser",
        })

    audit_df = pd.DataFrame(audit_rows)

    # Remove internal ranking columns from canonical output
    drop_cols = [c for c in canonical_df.columns if c.startswith("_")]
    canonical_df = canonical_df.drop(columns=drop_cols, errors="ignore")

    return canonical_df, audit_df