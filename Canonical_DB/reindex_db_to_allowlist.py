import json
import os
import tempfile
from pathlib import Path

import pandas as pd

db_path = Path("canonical_physchemprops.xlsx")
SCHEMA_ROOT = Path(r"C:\Users\vdevi\OneDrive - Lysning Innovation Consultants B.V\Lysning\Tools\Canonical_DB")
schema_path = SCHEMA_ROOT / "canonical_schema.json"

schema = json.loads(schema_path.read_text(encoding="utf-8"))
allow = schema.get("allowlist", [])

# de-dup allowlist preserving order (safety)
seen = set()
allow = [c for c in allow if not (c in seen or seen.add(c))]

# Ensure these required Henry columns are in the allowlist (idempotent)
required = [
    "henry_constant_mol_m3_Pa_25C",
    "log_henry_constant_mol_m3_Pa_25C",
    "source_henry_constant",
]
changed = False
for c in required:
    if c not in allow:
        allow.append(c)
        changed = True

# de-dup again after appending required (safety)
seen = set()
allow = [c for c in allow if not (c in seen or seen.add(c))]

if changed:
    schema["allowlist"] = allow
    schema_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")
    print("Updated schema allowlist (added missing Henry columns).")

df = pd.read_excel(db_path, engine="openpyxl")
df.columns = [str(c).strip() for c in df.columns]

df2 = df.reindex(columns=allow)  # adds missing columns as NA

# atomic write in same folder
fd, tmp = tempfile.mkstemp(prefix=db_path.stem + "__", suffix=db_path.suffix, dir=".")
os.close(fd)
tmp_path = Path(tmp)

df2.to_excel(tmp_path, index=False, engine="openpyxl", sheet_name="canonical")
os.replace(tmp_path, db_path)

print("DONE reindexed. rows:", len(df2), "cols:", len(df2.columns))
print("has henry_constant:", "henry_constant_mol_m3_Pa_25C" in df2.columns)