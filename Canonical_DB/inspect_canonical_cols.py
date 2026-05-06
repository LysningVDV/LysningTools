import pandas as pd
import json
from pathlib import Path

df = pd.read_excel("canonical_physchemprops.xlsx", engine="openpyxl")

print("rows:", len(df), "cols:", len(df.columns))

henry_like = [c for c in df.columns if "henry" in str(c).lower()]
print("henry cols:", henry_like)

exp_like = [c for c in df.columns if "experimental" in str(c).lower() and "henry" in str(c).lower()]
print("experimental henry-like cols:", exp_like)
print("repr(exp cols):", [repr(c) for c in exp_like])

# Also show exact presence checks
target = "experimental_henry_constant_mol_m3_pa"
print("has_exact_target:", target in df.columns)

SCHEMA_ROOT = Path(
    r"C:\Users\vdevi\OneDrive - Lysning Innovation Consultants B.V\Lysning\Tools\Canonical_DB"
)
schema_path = SCHEMA_ROOT / "canonical_schema.json"

schema = json.loads(schema_path.read_text(encoding="utf-8"))
allow = schema.get("allowlist", [])

print("\nSCHEMA allowlist_len:", len(allow))
print("SCHEMA has experimental_henry:", "experimental_henry_constant_mol_m3_pa" in allow)
print("SCHEMA has log_henry:", "log_henry_constant_mol_m3_Pa_25C" in allow)
print("SCHEMA has henry_constant:", "henry_constant_mol_m3_Pa_25C" in allow)

targets = [
    "henry_constant_mol_m3_Pa_25C",
    "log_henry_constant_mol_m3_Pa_25C",
    "experimental_henry_constant_mol_m3_pa",
    "source_henry_constant",
]
print("\nHENRY nonnull counts:")
for c in targets:
    if c in df.columns:
        print(c, int(df[c].notna().sum()))
    else:
        print(c, "MISSING")
