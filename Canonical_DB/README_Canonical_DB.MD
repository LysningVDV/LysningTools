# Canonical DB (Lysning Tools) — Local live DB + OneDrive governance/backups

This repository uses a **two-tier** setup for the canonical physchem properties database:

- **Live DB (authoritative)** lives on the **local machine** (not synced) for robustness.
- **Governance + backups** live in **OneDrive** for auditability and recovery.

This design prevents Excel truncation/corruption issues that can occur with sync clients and large `.xlsx` writes.

---

## 1) Locations (authoritative vs governance)

### 1.1 Live canonical DB (LOCAL, authoritative)
The live canonical database is stored locally:

- `%CANONICAL_DB_LOCAL_ROOT%\canonical_physchemprops.xlsx`

Example:
- `C:\Users\vdevi\AppData\Local\Lysning\Canonical_DB\canonical_physchemprops.xlsx`

This file is **not tracked in git** and should not be stored in OneDrive.

### 1.2 Governance root (OneDrive)
The governance root is the shared OneDrive folder:

- `...\OneDrive - Lysning Innovation Consultants B.V\Lysning\Tools\Canonical_DB`

It contains:
- `canonical_schema.json` (single source of truth for allowlist/schema)
- `canonical_audit_*.xlsx` (tool-specific audits)
- `canonical_physchemprops.rejected_*.xlsx` (rejected rows per tool)
- `backups/` (timestamped DB backups after each successful update)

---

## 2) Environment variables

### Required
- `CANONICAL_DB_LOCAL_ROOT`
  - points to the local folder that holds the live DB

Example (Windows):
- `CANONICAL_DB_LOCAL_ROOT=C:\Users\vdevi\AppData\Local\Lysning\Canonical_DB`

Check:
```bat
echo %CANONICAL_DB_LOCAL_ROOT%

3) Write safety: atomic writes + lock
All writes to the canonical DB use a shared atomic writer in canonical_common:

write to temp file in same directory
validate size threshold (when requested)
atomic os.replace(temp, final)
lock file: <target>.xlsx.lock

This prevents partial/truncated .xlsx files.

4) Canonical schema policy (allowlist)
The canonical schema is defined by:

Canonical_DB/canonical_schema.json (OneDrive governance root)

Policy:

schema file is authoritative
tools must not shrink schema implicitly
if a column should be removed, remove it explicitly from the schema JSON

%CANONICAL_DB_LOCAL_ROOT%\canonical_physchemprops.xlsx

Typical Windows example:


C:\Users\vdevi\AppData\Local\Lysning\Canonical_DB\canonical_physchemprops.xlsx

Properties:
- This file is **authoritative**
- It is **not committed to git**
- It must **not** be stored inside OneDrive
- All tools write exclusively to this file

---

### 1.2 Governance root (OneDrive — non-authoritative)

The governance root is stored in OneDrive:


...\OneDrive - Lysning Innovation Consultants B.V\Lysning\Tools\Canonical_DB

This folder contains:
- `canonical_schema.json` — **single source of truth** for DB schema
- `canonical_audit_physprops.xlsx`
- `canonical_audit_chem_annotator.xlsx`
- `canonical_physchemprops.rejected_*.xlsx`
- `backups/` — timestamped DB backups after each successful update

---

## 2. Environment variables

### Required


CANONICAL_DB_LOCAL_ROOT

Example (Windows):

CANONICAL_DB_LOCAL_ROOT=C:\Users\vdevi\AppData\Local\Lysning\Canonical_DB

Check:
```bat
echo %CANONICAL_DB_LOCAL_ROOT%

If this variable is unset or incorrect, tools will fail fast or behave unpredictably.

3. Atomic write safety and locking
All writes to the canonical DB go through canonical_common.write_xlsx_atomic.
Guarantees:

Write is performed to a temp file in the same directory
Optional minimum size validation prevents tiny/truncated outputs
Atomic replace via os.replace
A lock file (.xlsx.lock) prevents concurrent writers

Effect:

No partial Excel files
No OneDrive sync race conditions
No silent DB truncation

This is a hard safety invariant.

4. Canonical schema governance (allowlist)
Canonical columns are defined only by:
Canonical_DB/canonical_schema.json

Rules:

The schema file is authoritative
Tools must never implicitly add or drop columns
Column removal must be done explicitly in the schema JSON
Normalization is non-destructive (no filtering)

If schema drift occurs, repair using:
Canonical_DB/reindex_db_to_allowlist.py


5. Recommended tool execution order
Typical pipeline:

Lysning_CASResolver

CAS → InChI / InChIKey / SMILES


CAS_Structurer

CAS validation, repair, evidence scoring


Chem_Annotator

Descriptor / feature enrichment
Canonical DB update


PhysProps

HSP, Henry constants, physchem properties
Canonical DB update



Steps (3) and (4) both write to the same local DB and produce OneDrive backups.

6. Smoke and sanity checks
6.1 Verify DB size
A healthy DB is typically hundreds of KB or larger:
BATpython -c "import os; p=r'%CANONICAL_DB_LOCAL_ROOT%\canonical_physchemprops.xlsx'; print(os.path.getsize(p))"Show more lines

6.2 Run Chem_Annotator
BATcd ...\Tools\Chem_Annotatorpython -m chem_annotator.cliShow more lines

6.3 Run PhysProps (small test)
BATcd ...\Tools\PhysPropsphysprops input_cas_tst.xlsx output_cas_results.xlsxShow more lines

6.4 Run tests
BATcd ...\Tools\PhysPropspytest -qShow more lines

7. Backups and recovery
After each successful canonical update, a timestamped backup is written to:
Canonical_DB/backups/
canonical_physchemprops__YYYYMMDD_HHMMSS.xlsx

Recovery procedure:

Copy the newest good backup
Rename to canonical_physchemprops.xlsx
Place it in %CANONICAL_DB_LOCAL_ROOT%
Resume normal operation


8. Troubleshooting
Local DB missing
Restore from the newest OneDrive backup.
Worksheet named "canonical" not found
This indicates an incorrectly written DB.
Rewrite once using any tool configured with sheet_name="canonical" or reindex.
Schema mismatch
Ensure tools report using:
Canonical_DB/canonical_schema.json

Then reindex the local DB.

9. Henry constant policy
Canonical DB stores only:

henry_constant_mol_m3_Pa_25C
log_henry_constant_mol_m3_Pa_25C
source_henry_constant

Experimental aliases and duplicate representations are intentionally excluded to
avoid long-term ambiguity and schema instability.

---
