from __future__ import annotations

import pandas as pd
import numpy as np
import re
from pathlib import Path


# ============================================================
# Configuration
# ============================================================

# ------------------------------------------------------------------
# Input locations (explicit)
# ------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parents[2]

OUTPUT_DIR = BASE_DIR / "output" / "cas_public_ingest" / "discovery"

# ✅ choose the discovery run you want to consolidate
DISCOVERY_RUN = "GS_DISCOVERY_AROUND_1375541_OUTER"

GS_INPUT = OUTPUT_DIR / DISCOVERY_RUN / "goodscents_only_candidates.csv"
if not GS_INPUT.exists():
    raise FileNotFoundError(f"Missing GS CSV: {GS_INPUT}")
IFRA_INPUT = BASE_DIR / "output" / "cas_public_ingest" / "latest" / "ifra_dedup_by_cas.csv"

OUT_ENTITIES = Path("gs_entities_consolidated.csv")
OUT_CAS_MAP = Path("gs_entities_cas_map.csv")
OUT_SHADOWED = Path("gs_entities_shadowed.csv")


INVALID_NAMES = {
    "alpha", "beta", "gamma", "delta", "epsilon",
    "(r)", "(s)", "r", "s"
}


# ============================================================
# Helper functions
# ============================================================

def normalize_name(name: str) -> str:
    """Light normalization for name matching."""
    return re.sub(r"[^a-z0-9\s]", "", name.lower()).strip()


def clean_primary_name(name: str | None):
    """
    Returns:
        clean_name, name_confidence, needs_name_curation
    """
    if not isinstance(name, str):
        return None, "low", True

    n = name.strip().lower()

    if (
        n in INVALID_NAMES
        or len(n) < 5
        or re.fullmatch(r"[\d\-]+", n)
    ):
        return None, "low", True

    if re.search(r",\s*\d+$", n):
        return name.strip(), "medium", False

    return name.strip(), "high", False


def classify_entity(cas_count: int, name: str | None):
    lname = (name or "").lower()

    if cas_count > 1 and lname in INVALID_NAMES:
        return "stereo_family", "multi-CAS with symbolic name"

    if cas_count > 1:
        return "stereo_family", "multi-CAS GS material"

    if "reaction product" in lname or "acetal" in lname:
        return "reaction_product", "reaction product wording"

    if "oil" in lname or "terpen" in lname:
        return "mixture_like", "oil / terpene wording"

    if cas_count == 1:
        return "monomer", "single-CAS GS material"

    return "unknown", "fallback"


# ============================================================
# Load inputs
# ============================================================

df_gs_raw = pd.read_csv(GS_INPUT, dtype={"cas": str, "rw_id": int})
df_ifra = pd.read_csv(IFRA_INPUT, dtype=str)
print("IFRA columns:", df_ifra.columns.tolist())

df_ifra["cas"] = df_ifra["cas"].astype(str)
# ------------------------------------------------------------
# Detect IFRA name column robustly
# ------------------------------------------------------------

NAME_CANDIDATES = [
    "material_name",
    "principal_names",
    "name",
    "designation",
    "substance_name",
    "display_name",
    "ifra_name",
]

ifra_name_col = None
for c in NAME_CANDIDATES:
    if c in df_ifra.columns:
        ifra_name_col = c
        break

if ifra_name_col is None:
    raise KeyError(
        "Could not find IFRA name column. "
        f"Available columns: {df_ifra.columns.tolist()}"
    )

print(f"Using IFRA name column: {ifra_name_col}")

df_ifra["name_norm"] = (
    df_ifra[ifra_name_col]
    .astype(str)
    .apply(normalize_name)
)

IFRA_CAS_SET = set(df_ifra["cas"])
IFRA_NAME_SET = set(df_ifra["name_norm"])


# ============================================================
# Consolidate GS entities (rw_id centric)
# ============================================================

entities = []

for rw_id, g in df_gs_raw.groupby("rw_id"):
    cas_list = sorted(set(g["cas"].dropna()))
    cas_count = len(cas_list)

    raw_names = g["primary_name"].dropna().astype(str)
    chosen_name = None
    name_confidence = "low"
    needs_name_curation = True

    for n in raw_names:
        clean, conf, needs = clean_primary_name(n)
        if clean:
            chosen_name = clean
            name_confidence = conf
            needs_name_curation = needs
            break

    entity_class, class_basis = classify_entity(cas_count, chosen_name)

    entities.append({
        "gs_entity_id": f"GS:rw{rw_id}",
        "rw_id": rw_id,
        "source": "GoodScents",
        "source_url": g["source_url"].iloc[0],

        "primary_name": chosen_name,
        "name_confidence": name_confidence,
        "needs_name_curation": needs_name_curation,

        "cas_list": cas_list,
        "cas_count": cas_count,
        "multi_cas_source": cas_count > 1,

        "entity_class": entity_class,
        "classification_basis": class_basis,

        "discovered_at": g["discovered_at"].min(),

        # defaults (will be updated below)
        "ifra_relation": "none",
        "ifra_evidence": None,

        "eligible_for_auto_use": False,
        "eligible_for_review": True,
        "eligible_for_rejection": entity_class == "mixture_like",
    })


df_entities = pd.DataFrame(entities)


# ============================================================
# IFRA shadow detection
# ============================================================

def detect_ifra_shadow(row):
    evidence = []

    # CAS-based shadow
    cas_hits = set(row["cas_list"]) & IFRA_CAS_SET
    if cas_hits:
        evidence.append(f"CAS overlap: {', '.join(sorted(cas_hits))}")

    # Name-based shadow (conservative)
    if isinstance(row["primary_name"], str):
        n_norm = normalize_name(row["primary_name"])
        if n_norm in IFRA_NAME_SET:
            evidence.append("name normalized match")

    if evidence:
        return "equivalent", "; ".join(evidence)

    return "none", None


shadow_results = df_entities.apply(
    lambda r: detect_ifra_shadow(r),
    axis=1,
    result_type="expand",
)

df_entities[["ifra_relation", "ifra_evidence"]] = shadow_results

df_entities.loc[df_entities["ifra_relation"] != "none", "eligible_for_auto_use"] = False


# ============================================================
# Outputs
# ============================================================

df_entities.to_csv(OUT_ENTITIES, index=False)

df_entities.explode("cas_list") \
    .rename(columns={"cas_list": "cas"}) \
    .to_csv(OUT_CAS_MAP, index=False)

df_entities[df_entities["ifra_relation"] != "none"] \
    .to_csv(OUT_SHADOWED, index=False)

print("✅ GS consolidation + IFRA shadow detection complete")
print(f"Entities written: {OUT_ENTITIES}")
print(f"CAS map written: {OUT_CAS_MAP}")
print(f"IFRA-shadowed entities: {OUT_SHADOWED}")