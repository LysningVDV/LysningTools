import json
from pathlib import Path

schema_path = Path(r"C:\Users\vdevi\OneDrive - Lysning Innovation Consultants B.V\Lysning\Tools\Canonical_DB\canonical_schema.json")
data = json.loads(schema_path.read_text(encoding="utf-8"))
allow = data.get("allowlist", [])

drop = "experimental_henry_constant_mol_m3_pa"
before = len(allow)
allow = [c for c in allow if str(c).strip() != drop]
after = len(allow)

data["allowlist"] = allow
schema_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

print("before", before, "after", after, "dropped", (before != after))