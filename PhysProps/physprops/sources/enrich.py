from pathlib import Path
import pandas as pd

from physprops.sources.hsp_compute import compute_hsp_triplet_from_chemicals  # [1](https://lysninginnovationconsultant-my.sharepoint.com/personal/villeneuve_lysning_nl/Documents/Microsoft%20Copilot%20Chat%20Files/hsp_compute.py)
from physprops.sources.hsp_wdr import WDRHSPDatabase  # [2](https://lysninginnovationconsultant-my.sharepoint.com/personal/villeneuve_lysning_nl/Documents/Microsoft%20Copilot%20Chat%20Files/hsp_wdr.py)

def enrich_hsp_columns(out_wide: pd.DataFrame) -> pd.DataFrame:
    """
    Adds / populates:
      experimental_hsp_delta_{d,p,h}_mpa05, source_hsp
      computed_hsp_delta_{d,p,h}_mpa05, source_hsp_computed
    Deterministic: does not randomize; fills from available identifiers.
    """
    df = out_wide.copy()

    # Ensure required identifier columns exist
    if "inchi_key" not in df.columns:
        # no key => can't match WDR
        return df

    # ---- 1) Measured HSP from WDR by InChIKey ----
    # Adjust this path to where your CSV is located (based on your tree)
    csv_path = Path(__file__).resolve().parent / "hsp_wdr" / "JoshuaSchrier_Hansen-Solubility-Parameters.csv"
    if csv_path.exists():
        wdr = WDRHSPDatabase(csv_path)
        exp_d, exp_p, exp_h, exp_src = [], [], [], []
        for ik in df["inchi_key"].astype(str):
            triplet, src, warn = wdr.lookup_measured(ik)  # (triplet, source_string, warning_token)
            if triplet is None:
                exp_d.append(pd.NA); exp_p.append(pd.NA); exp_h.append(pd.NA); exp_src.append(pd.NA)
            else:
                exp_d.append(triplet.delta_d_mpa05)
                exp_p.append(triplet.delta_p_mpa05)
                exp_h.append(triplet.delta_h_mpa05)
                exp_src.append(src)

        df["experimental_hsp_delta_d_mpa05"] = exp_d
        df["experimental_hsp_delta_p_mpa05"] = exp_p
        df["experimental_hsp_delta_h_mpa05"] = exp_h
        df["source_hsp"] = exp_src

    # ---- 2) Computed HSP from chemicals.solubility by CASRN ----
    # prefer canonical cas_number if present; else CAS_ID/cas
    cas_col = "cas_number" if "cas_number" in df.columns else ("CAS_ID" if "CAS_ID" in df.columns else ("cas" if "cas" in df.columns else None))
    if cas_col is not None:
        comp_d, comp_p, comp_h, comp_src = [], [], [], []
        for casrn in df[cas_col].tolist():
            triplet, src, warn = compute_hsp_triplet_from_chemicals(casrn)  # [1](https://lysninginnovationconsultant-my.sharepoint.com/personal/villeneuve_lysning_nl/Documents/Microsoft%20Copilot%20Chat%20Files/hsp_compute.py)
            if triplet is None:
                comp_d.append(pd.NA); comp_p.append(pd.NA); comp_h.append(pd.NA); comp_src.append(pd.NA)
            else:
                comp_d.append(triplet.delta_d_mpa05)
                comp_p.append(triplet.delta_p_mpa05)
                comp_h.append(triplet.delta_h_mpa05)
                comp_src.append(src)

        df["computed_hsp_delta_d_mpa05"] = comp_d
        df["computed_hsp_delta_p_mpa05"] = comp_p
        df["computed_hsp_delta_h_mpa05"] = comp_h
        df["source_hsp_computed"] = comp_src

    return df


def enrich_henry_columns(out_wide: pd.DataFrame) -> pd.DataFrame:
    """
    Populate Henry's-law columns in the wide export using the local Sander Henry DB.

    Adds/updates (kept deterministic in schema even if not filled):
      - henry_constant_mol_m3_Pa_25C
      - log_henry_constant_mol_m3_Pa_25C
      - source_henry_constant

    Join key: inchi_key
    """
    if out_wide is None or len(out_wide) == 0:
        return out_wide

    if "inchi_key" not in out_wide.columns:
        return out_wide

    # Ensure output columns exist deterministically
    target_cols = (
        "henry_constant_mol_m3_Pa_25C",
        "log_henry_constant_mol_m3_Pa_25C",
        "source_henry_constant",
    )
    for c in target_cols:
        if c not in out_wide.columns:
            out_wide[c] = pd.NA

    # Lazy import to avoid import-time side effects
    try:
        from physprops.sources.Sander_henry.sander_henry import SanderHenryDatabase
    except Exception:
        # If module is unavailable, keep columns but do not fail the pipeline
        return out_wide

    # Instantiate DB (should build/open local cache)
    try:
        db = SanderHenryDatabase()
    except Exception:
        return out_wide

    # Fill deterministically row-by-row
    for i, ik in out_wide["inchi_key"].items():
        if not isinstance(ik, str) or not ik.strip():
            continue
        ik2 = ik.strip().upper()

        try:
            rec = db.lookup_by_inchikey(ik2)
        except Exception:
            rec = None

        if rec is None:
            continue

        wrote_any = False

        if getattr(rec, "henry_constant_mol_m3_Pa_25C", None) is not None:
            out_wide.at[i, "henry_constant_mol_m3_Pa_25C"] = rec.henry_constant_mol_m3_Pa_25C
            wrote_any = True

        if getattr(rec, "log_henry_constant_mol_m3_Pa_25C", None) is not None:
            out_wide.at[i, "log_henry_constant_mol_m3_Pa_25C"] = rec.log_henry_constant_mol_m3_Pa_25C
            wrote_any = True

        if wrote_any:
            out_wide.at[i, "source_henry_constant"] = getattr(rec, "source", "Sander Henry DB")

    return out_wide