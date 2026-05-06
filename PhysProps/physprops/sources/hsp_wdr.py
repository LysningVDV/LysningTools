from __future__ import annotations

import re
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import pandas as pd


# -----------------------------------------------------------------------------
# WDR resource metadata (warning-only update check)
# -----------------------------------------------------------------------------
WDR_HSP_RESOURCE_URL = (
    "https://datarepository.wolframcloud.com/resources/"
    "JoshuaSchrier_Hansen-Solubility-Parameters"
)
# WDR page currently shows: "Date Created: 1 May 2020" (pinned for update warnings)
WDR_HSP_PINNED_DATE_CREATED = "1 May 2020"


# -----------------------------------------------------------------------------
# Parsing helpers
# -----------------------------------------------------------------------------
# Raw CSV values may look like:
#   Quantity[17., Sqrt["Megapascals"]]
# We keep Hansen units as sqrt(MPa), i.e. MPa^0.5.

_QUANTITY_RE = re.compile(
    r"""Quantity\[\s*
        (?P<num>[-+]?\d+(?:\.\d*)?(?:[eE][-+]?\d+)?)  # 17. or 17.0 or 17 or 1e-3
        \s*,\s*Sqrt\[\s*["']?Megapascals["']?\s*\]\s*
        \]\s*$""",
    re.VERBOSE,
)


def _parse_quantity_sqrt_mpa(x) -> float:
    """
    Parse Mathematica Quantity[17., Sqrt["Megapascals"]] -> 17.0

    Returns np.nan on failure.
    """
    if x is None:
        return np.nan

    if isinstance(x, (int, float, np.number)):
        return float(x)

    s = str(x).strip()
    if not s or s.lower() in {"nan", "none"}:
        return np.nan

    # Fast path: plain numeric string
    try:
        return float(s)
    except Exception:
        pass

    m = _QUANTITY_RE.match(s)
    if not m:
        return np.nan

    try:
        return float(m.group("num"))
    except Exception:
        return np.nan


# -----------------------------------------------------------------------------
# Public data structures
# -----------------------------------------------------------------------------
@dataclass(frozen=True)
class HSPTriplet:
    """Generic triplet (kept for compatibility / debug helpers)."""
    delta_d_mpa05: float
    delta_p_mpa05: float
    delta_h_mpa05: float


@dataclass(frozen=True)
class HSPTripletMPA05:
    """
    Hansen solubility parameters in MPa^0.5 (sqrt(MPa)).
    """
    delta_d_mpa05: float
    delta_p_mpa05: float
    delta_h_mpa05: float


# -----------------------------------------------------------------------------
# Update warning (non-blocking)
# -----------------------------------------------------------------------------
def check_for_wdr_hsp_update(timeout_seconds: float = 2.0) -> Optional[str]:
    """
    Warning-only check: fetches the WDR resource page and tries to parse the
    'Date Created' metadata. If it differs from WDR_HSP_PINNED_DATE_CREATED,
    warns that a newer/changed dataset may exist.

    - Never fails pipeline if offline.
    - Returns the parsed 'Date Created' string if it differs, else None.

    The WDR page includes a "Date Created" metadata field.
    """
    try:
        import requests
    except Exception:
        # Optional dependency; skip silently
        return None

    try:
        resp = requests.get(WDR_HSP_RESOURCE_URL, timeout=timeout_seconds)
        resp.raise_for_status()
        html = resp.text
    except Exception as e:
        warnings.warn(
            f"WDR HSP update check skipped (network unavailable): {e}",
            RuntimeWarning,
        )
        return None

    m = re.search(r"Date Created:\s*([^<\n\r]+)", html)
    if not m:
        warnings.warn(
            "WDR HSP update check failed: could not parse 'Date Created' from page.",
            RuntimeWarning,
        )
        return None

    date_created = m.group(1).strip()
    if date_created != WDR_HSP_PINNED_DATE_CREATED:
        warnings.warn(
            f"WDR HSP dataset metadata changed: Date Created is '{date_created}' "
            f"(pinned '{WDR_HSP_PINNED_DATE_CREATED}'). Consider re-downloading CSV. "
            f"See {WDR_HSP_RESOURCE_URL}",
            RuntimeWarning,
        )
        return date_created

    return None


# -----------------------------------------------------------------------------
# WDR loader + lookup
# -----------------------------------------------------------------------------
class WDRHSPDatabase:
    """
    Loads WDR HSP CSV (Schrier/Zeng et al.) and provides measured/reference HSP triplets.

    Notes grounded in WDR resource:
    - Dataset consists of HSP values for common solvents at 25°C.
    - Entries are identified by InChIKeys.

    Raw CSV header (typical):
      "Solvent","InChIKey","Volume","δd","δp","δh","δt"

    We normalize internal columns:
      solvent_raw, inchi_key, volume_raw, delta_d_raw, delta_p_raw, delta_h_raw, delta_t_raw

    And parse numeric columns (MPa^0.5):
      delta_d, delta_p, delta_h
    """

    # After normalization we expect to have at least inchi_key and some form of delta columns.
    REQUIRED_COLUMNS_AFTER_NORMALIZATION = ["inchi_key"]

    def __init__(self, csv_path):
        self.csv_path = csv_path
        self.df = self._load_csv(csv_path)

        # Build deterministic lookup map used by lookup_measured(): inchi_key -> DataFrame
        # (lookup_measured uses self.by_inchikey.get(...))
        if self.df is not None and len(self.df) > 0 and "inchi_key" in self.df.columns:
            # Ensure keys are canonical uppercase (should already be done in _normalize_columns)
            self.df["inchi_key"] = self.df["inchi_key"].astype(str).str.strip().str.upper()
            # Dict (not GroupBy) so .get() works exactly as used in lookup_measured()
            self.by_inchikey = {k: g for k, g in self.df.groupby("inchi_key", sort=False)}
        else:
            self.by_inchikey = {}

        # Optional secondary index (kept for debug / speed)
        # Stored as: ik -> (d, p, h, src)
        self._idx = {}
        if self.df is not None and len(self.df) > 0:
            required = {"inchi_key", "delta_d", "delta_p", "delta_h"}
            missing = required - set(self.df.columns)
            if not missing:
                for _, row in self.df.iterrows():
                    ik = row.get("inchi_key", None)
                    if not isinstance(ik, str) or not ik:
                        continue

                    ik = ik.strip().upper()
                    d = row.get("delta_d", np.nan)
                    p = row.get("delta_p", np.nan)
                    h = row.get("delta_h", np.nan)

                    if pd.isna(d) or pd.isna(p) or pd.isna(h):
                        continue

                    if ik not in self._idx:
                        self._idx[ik] = (float(d), float(p), float(h), "WDR")

    def _normalize_columns(self, df):
        df = df.copy()
        df.columns = [
            str(c).strip().lower()
            .replace(" ", "_")
            .replace("-", "_")
            .replace("__", "_")
            for c in df.columns
        ]

        # Map known WDR column variants -> canonical names
        rename_map = {
            "inchikey": "inchi_key",
            "inchi_key": "inchi_key",
            "inchi": "inchi",
            "smiles": "smiles",
            "solvent": "solvent_raw",
            "solvent_raw": "solvent_raw",
            "volume": "volume_raw",
            "volume_raw": "volume_raw",
            # raw hsp (mathematica strings)
            "delta_d_raw": "delta_d_raw",
            "delta_p_raw": "delta_p_raw",
            "delta_h_raw": "delta_h_raw",
            "delta_t_raw": "delta_t_raw",
            # numeric hsp (sometimes already present)
            "delta_d": "delta_d",
            "delta_p": "delta_p",
            "delta_h": "delta_h",
            
            # WDR unicode headers for Hansen parameters
            "δd": "delta_d_raw",
            "δp": "delta_p_raw",
            "δh": "delta_h_raw",
            "δt": "delta_t_raw",

        }
        df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
        # Robust fallback for unicode delta headers that may not match exactly due to normalization
        for ucol, raw_col in (("δd", "delta_d_raw"), ("δp", "delta_p_raw"), ("δh", "delta_h_raw"), ("δt", "delta_t_raw")):
            if raw_col in df.columns:
                continue
            hit = None
            for c in df.columns:
                if str(c).strip() == ucol:
                    hit = c
                    break
            if hit is not None:
                df[raw_col] = df[hit]
        # Ensure inchi_key exists and is cleaned
        if "inchi_key" in df.columns:
            df["inchi_key"] = (
                df["inchi_key"].astype(str)
                .str.strip()
                .str.upper()
                .replace({"NAN": np.nan, "NONE": np.nan, "": np.nan})
            )

        # Ensure numeric delta_d/p/h exist; prefer existing numeric columns; otherwise parse *_raw
        for comp in ("d", "p", "h"):
            num_col = f"delta_{comp}"
            raw_col = f"delta_{comp}_raw"

            if num_col in df.columns:
                df[num_col] = pd.to_numeric(df[num_col], errors="coerce")

            if (num_col not in df.columns) and (raw_col in df.columns):
                df[num_col] = df[raw_col].map(_parse_quantity_sqrt_mpa)

            # If both exist: fill numeric gaps from raw parse
            if (num_col in df.columns) and (raw_col in df.columns):
                parsed = df[raw_col].map(_parse_quantity_sqrt_mpa)
                df[num_col] = df[num_col].fillna(parsed)

        return df

    def _load_csv(self, csv_path: Path) -> pd.DataFrame:
        df = pd.read_csv(csv_path, sep=None, engine="python", encoding="utf-8")

        # Normalize headers / create standardized columns
        df = self._normalize_columns(df)

        # If raw columns exist, ensure numeric columns are populated (fill gaps only)
        # (This complements _normalize_columns without overwriting already-good numerics.)
        for comp in ("d", "p", "h"):
            raw_col = f"delta_{comp}_raw"
            num_col = f"delta_{comp}"
            if raw_col in df.columns:
                parsed = df[raw_col].map(_parse_quantity_sqrt_mpa)
                if num_col in df.columns:
                    df[num_col] = pd.to_numeric(df[num_col], errors="coerce").fillna(parsed)
                else:
                    df[num_col] = parsed

        return df

    def lookup_measured(
        self,
        inchikey: Optional[str],
    ) -> Tuple[Optional[HSPTripletMPA05], Optional[str], Optional[str]]:
        """
        Deterministic measured/reference lookup by exact InChIKey.

        Returns:
        (triplet, source_string, warning_token)

        All-or-none:
        - Only returns a triplet if delta_d, delta_p, delta_h are all present (not NaN).
        - Otherwise returns None and a warning token.

        Source string includes @25C as dataset is defined at 25°C.
        """
        if not inchikey or not str(inchikey).strip():
            return None, None, "HSP measured missing (no InChIKey)"

        inchikey = str(inchikey).strip().upper()
        grp = self.by_inchikey.get(inchikey)
        if grp is None or len(grp) == 0:
            return None, None, "HSP measured missing (no WDR match by InChIKey)"

        row = grp.iloc[0]  # deterministic: first row wins
        d, p, h = row.get("delta_d", np.nan), row.get("delta_p", np.nan), row.get("delta_h", np.nan)

        if pd.notna(d) and pd.notna(p) and pd.notna(h):
            triplet = HSPTripletMPA05(float(d), float(p), float(h))
            src = (
                "Wolfram Data Repository (Schrier/Zeng et al.) HSP @25C; "
                "units=sqrt(MPa); "
                f"id=InChIKey={inchikey}"
            )
            return triplet, src, None

        # Missing or parse failed for at least one component
        return None, None, 'HSP measured parse failed (expected Quantity[..., Sqrt["Megapascals"]])'

    def lookup_measured_idx(self, inchi_key: str):
        """
        Debug/back-compat helper: Lookup measured HSP (WDR) by InChIKey using _idx.
        Returns (triplet, source_str, warning_or_None).
        """
        if inchi_key is None:
            return None, None, "missing_inchikey"

        ik = str(inchi_key).strip().upper()
        if not ik:
            return None, None, "missing_inchikey"

        hit = self._idx.get(ik)
        if hit is None:
            return None, None, "not_found"

        d, p, h, src = hit
        return HSPTriplet(d, p, h), src, None