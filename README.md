Tools/
├─ pipeline_inputs/        # Customer input files (ignored by git)
├─ output/                 # All generated run artifacts (ignored by git)
│
├─ CAS_Structurer/         # CAS parsing & normalization
├─ Lysning_CASResolver/    # CAS → InChIKey / SMILES resolution
├─ Chem_Annotator/         # Structural descriptors & group counts
├─ PhysProps/              # Physico-chemical property enrichment
│
├─ Canonical_DB/           # Governance, DB2 scripts, CAS view exports
│  └─ scripts/
│     ├─ pipeline_run_customer.py
│     ├─ upsert_customer_map.py
│     └─ smoke_db2_view_export.py
│
├─ canonical_common/       # Shared canonical logic
└─ README.md               # This file

---

## 📥 Inputs: `pipeline_inputs/` (per customer)

Customer inputs live under:


pipeline_inputs/
└─ <CUSTOMER_ID>/
└─ /
├─ input.xlsx
└─ columns.json   (recommended)

Example:


pipeline_inputs/<customer>/2026-05-08/input.xlsx

### Required input columns (explicit per file)
Column names are **not assumed** and must be provided explicitly.

Typical mapping:
- CAS column (e.g. `CAS_ID`)
- Customer code (e.g. `ING_ID`)
- Name / designation (e.g. `Name`)

Optional helper file:

```json
{
  "customer_id": "<customer>",
  "sheet": 0,
  "cas_col": "CAS_ID",
  "code_col": "ING_ID",
  "name_col": "Name"
}


pipeline_inputs/ is intentionally ignored by git.


▶️ Running the pipeline (single customer)
The primary entry point is:
Shellpython Canonical_DB/scripts/pipeline_run_customer.pyShow more lines
✅ Full end‑to‑end run
Shellpython Canonical_DB/scripts/pipeline_run_customer.py \  pipeline_inputs/<customer>/2026-05-08/input.xlsx \  --customer-id <customer> \  --cas-col "CAS_ID" \  --code-col "ING_ID" \  --name-col "Name"Show more lines
This runs, in order:

CAS_Structurer
CASResolver
DB2 customer_map upsert
Per-customer CAS view export
Chem_Annotator (DB1 enrichment)
PhysProps (DB1 enrichment)
Final per-customer CAS view export

🔄 Fast runs (skip heavy steps)
Shell--skip-chem        # Skip Chem_Annotator--skip-physprops   # Skip PhysPropsShow more lines
Example (Phase‑1 only):
Shellpython Canonical_DB/scripts/pipeline_run_customer.py \  pipeline_inputs/<customer>/2026-05-08/input.xlsx \  --customer-id <customer> \  --cas-col "CAS_ID" \  --code-col "ING_ID" \  --name-col "Name" \  --skip-chem --skip-physpropsShow more lines

📤 Outputs
All run artifacts are written to standardized locations:
Tool outputs
output/
├─ CAS_Structurer/
├─ CASResolver/
├─ Chem_Annotator/
├─ physprops/
├─ PipelineRunner/
└─ Canonical_DB/
   └─ exports_cas_view/

Each run produces timestamped files + a manifest JSON where applicable.
Per‑customer CAS views
output/Canonical_DB/exports_cas_view/
├─ cas_view__<customer>__<timestamp>.xlsx
├─ cas_view__<customer>__<timestamp>.csv
├─ cas_view_joinable__<customer>__<timestamp>.xlsx
└─ cas_view_joinable__<customer>__<timestamp>.csv

These include:

Canonical DB1 properties
DB2 registry metadata
Customer overlay (Customer Code / Code Unique, Name)


🧱 Canonical databases
DB1 – Canonical PhysChem DB

Keyed by InChIKey
Enriched by:

Chem_Annotator
PhysProps


Location (local):
%LOCALAPPDATA%/Lysning/Canonical_DB/canonical_physchemprops.xlsx


Governance:

Allowlist schema
Atomic writes
Audit trail + backups



DB2 – CAS Registry

Location (local):
%LOCALAPPDATA%/Lysning/Canonical_DB/cas_registry.xlsx


Sheets:

registry — CAS ↔ InChIKey
customer_map — customer overlays (latest wins per CAS/customer)




🧪 Testing
Run the full test suite:
Shellpytest -qShow more lines
Test categories

Unit tests: CAS parsing & strict header handling
Integration tests:

DB2 customer_map upsert logic
Per‑customer CAS view overlay export



Markers:

integration
slow

Example:
Shellpytest -q -m integrationpytest -q -m "not slow"Show more lines

✅ Design decisions (intentional)

No implicit column names → explicit mapping enforced
Customer data never contaminates DB1
CAS views are the only customer-facing exports
No background services or cloud dependencies
One-command reproducibility with full audit trail


📌 Status
✅ Pipeline runner stable
✅ End-to-end tested
✅ Governance enforced
✅ Ready for production use (single-operator)
Next likely extensions:

Auto‑loading columns.json
Dry‑run mode
Multi‑customer batch runner

# Lysning Chemical Data Pipeline# Lysning Chemical Data Pipeline into **canonical, governed chemical datasets** and
**per-customer CAS views** enriched with structural, descriptor, and physico‑chemical data.

The pipeline is designed for **single-operator use**, strict schema governance,
and full auditability.

---

## 🧭 High-level overview

**Core principles**
- Local-first (no cloud dependency required)
- Deterministic, reproducible outputs
- Strict column/schema governance
- Canonical DB separated from customer-specific data
- Clear separation between **code**, **run artifacts**, and **customer inputs**

**Two canonical databases**
- **DB1** – Canonical phys/chem properties (InChIKey-keyed)
- **DB2** – CAS registry + customer overlays

---

## 🗂 Repository layout

This repository contains a **local-first, deterministic chemical data pipeline** for


🚀 Quick start (operator cheat sheet)
This pipeline is designed to be run from a local Anaconda environment.
1) Environment setup (always start here)
Shellconda activate rdkit-envShow more lines
All tools assume this environment is active.

2) Editable installs (run once per environment)
These tools are installed in editable mode so that code changes are picked up immediately.
Shellcd "C:\Users\vdevi\OneDrive - Lysning Innovation Consultants B.V\Lysning\Tools\PhysProps"pip install -e .cd "C:\Users\vdevi\OneDrive - Lysning Innovation Consultants B.V\Lysning\Tools\Chem_Annotator"pip install -e .Show more lines

CAS_Structurer and CASResolver are used via python -m and do not require separate installation.


3) Working directory
All commands below assume you are in the Tools repository root unless stated otherwise:
Shellcd "C:\Users\vdevi\OneDrive - Lysning Innovation Consultants B.V\Lysning\Tools"Show more lines

🧩 Individual tools (for debugging or standalone use)
These commands are mainly useful for diagnostics, development, or testing.
For production runs, prefer the pipeline runner.

CAS_Structurer – CAS parsing & normalization
Splits, normalizes, validates CAS entries from customer files.
Shellpython -m cas_structurer "CAS_input.xlsx" --customer-id <CUSTOMER_ID>Show more lines
Strict column mapping is supported (recommended in pipeline usage):
Shell--cas-col <CAS_COLUMN>--code-col <CUSTOMER_CODE_COLUMN>--name-col <NAME_COLUMN>Show more lines

Lysning_CASResolver – CAS → InChIKey / SMILES
Resolves CAS numbers into structure identifiers and updates DB2.
Shellpython -m lysning_casresolver.main input_cas.xlsxShow more lines

Output defaults to Tools/output/CASResolver/
Also updates the local DB2 registry


Chem_Annotator – structural descriptors & functional groups
Annotates molecules based on SMILES / InChIKey input.
Shellpython -m chem_annotator.cliShow more lines

Reads Chem_Annotator/smiles.xlsx
Writes run artifacts to:
Tools/output/Chem_Annotator/



Run tests for Chem_Annotator only:
Shellpytest -q Chem_AnnotatorShow more lines

PhysProps – physico‑chemical properties
Adds public-domain physico‑chemical properties (e.g. MW, HSP, Henry).
Shellpython -m physprops.main PhysProps/input_inchikey.xlsx --log INFO``Show more lines
Outputs:
Tools/output/physprops/


🧪 Tests
Run all tests:
Shellpytest -qShow more lines
Run only integration tests:
Shellpytest -q -m integrationShow more lines
Run everything except slow tests:
Shellpytest -q -m "not slow"