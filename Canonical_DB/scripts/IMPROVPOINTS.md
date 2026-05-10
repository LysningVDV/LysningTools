UPDATED PLAN:
✅ Keep DB1/DB2 live databases in %LOCALAPPDATA%/Lysning/Canonical_DB/
✅ Keep audit/backups under Tools/Canonical_DB/
✅ .gitignore ignores:

pipeline_inputs/ (customer files)
output/ (run artifacts)
Canonical_DB/exports_pipeline/ (intermediate glue)


✅ Per-customer CAS view export (--customer-id) with suffixes
✅ DB2 customer_map sheet + “latest wins” upsert
✅ Lightweight pipeline runner (single-customer sequential)
✅ Minimal tests for:

CAS_Structurer strict mapping
DB2 upsert latest wins
per-customer overlay export


✅ README draft + “operator cheat sheet” integration work started

Status: ✅ done (core), 🟡 README polishing ongoing

Phase 1 — Point A: CASResolver + PhysProps robustness & speed (your chosen focus)
A1) Sleep prevention in CASResolver

✅ Implemented and verified: “Sleep prevention activated.”

A2) DB2-first conservative caching in CASResolver

✅ Implemented and verified:

“DB2 cache enabled (eligible entries=1327)”
“Cached via DB2: 1312”
“DB2 cache misses: 1743”


✅ Added cache stats to printed summary
🟡 Mode clarity: decide behavior on misses (see A2.2 below)

A2.2) Add explicit --cache-only flag (recommended)
This is the “make behavior explicit” step:

Default: cache-first then resolve misses
--cache-only: cache-first and do not resolve misses

Status: ❌ not yet implemented (but very small change)
A3) Negative caching for hopeless cases (optional tail control)

Skip retrying repeated unresolved entries unless --force or stale threshold

Status: ❌ not implemented
A4) RDKit parse hardening (SMILES + InChI)

✅ Implemented at the choke point:

strip |...| from SMILES
guard InChI parsing (startswith("InChI="))
keep debug logs



A5) Optional: reduce RDKit warning spam

Add --quiet-rdkit-warn to disable rdApp.warning during batch runs

Status: ❌ not implemented
A6) Optional: honest timing (wall vs active)

Report both datetime.now(UTC) (wall) and perf_counter() (active)

Status: ❌ not implemented
B1) PhysProps DB1-first skip (high value)

Skip PubChem lookups for InChIKeys already complete in DB1
Reduces network calls and transient errors

Status: ❌ not implemented
Phase 1 status: ✅ major wins landed; 🟡 one key small UX flag remaining (--cache-only); ❌ PhysProps caching still pending

Phase 2 — Option C: DB1 structure completeness (your preference)
You strongly want DB1 to have SMILES/InChI for more than 756/1555 rows.
C1) Add explicit DB1 structure backfill tool (recommended first step)
New script:

Canonical_DB/scripts/backfill_db1_structures.py

Policy:

Backfill DB1 rows where inchi_key exists but smiles/inchi missing
Source priority:

DB2 registry (local, preferred)
PubChem lookup by InChIKey (cached, fallback)


Only for joinable cas_status == valid by default
Provenance fields + audit + manifest
Never overwrite existing unless --force

Status: ❌ not implemented
C2) Later: centralize DB1 identity normalization (dual-identity policy)

If SMILES exists and InChIKey missing → DB1 mints InChIKey deterministically
SMILES stays “functional representation”, InChIKey is canonical identity

Status: ❌ not implemented (concept agreed)

Phase 3 — Authority vs Customer semantics (your earlier architectural points)
These were explicitly identified as “later refinements” and remain in the plan.
S1) Introduce dataset_role = customer|authority

e.g., --dataset-role authority --authority IFRA

Status: ❌ not implemented
S2) CAS_Structurer authority mode (no customer code required)

customer_code optional
dedupe keys become CAS-only (or customer_id+CAS)
eliminate “fake codes” for authority datasets

Status: ❌ not implemented
S3) Keep GS reference-only + compatible with dual identity

GS can contribute SMILES
never mints identity
only enters DB1 through governed step

Status: ✅ policy decided, implementation later

Phase 4 — Runner ergonomics & docs polish
R1) Runner auto-load columns.json

avoid manual casing mistakes (Name vs NAME)
reproducibility

Status: ❌ not implemented
R2) Runner --dry-run

print planned commands + paths, no execution

Status: ❌ not implemented
D1) Finalize README set

top-level README + optional tool READMEs
include “known warnings” section (RDKit stereo/protonation, CXSMILES pipe stripping)
include “modes” section: cache-only vs resolve-misses vs force-refresh

Status: 🟡 partially done (draft exists; needs consolidation)

##############################################################################
PREVIOUS PLAN - DOUBLECHECK WHETHER EERYTHING COVERED!
##############################################################################

Key Improvement Points (Agreed Direction)
1. Make Authority vs Customer an Explicit Concept in Tooling
Current situation

CAS_Structurer and the customer pipeline implicitly assume every input is customer‑scoped.
This forces authority data (IFRA) to masquerade as customer data (fake “Customer Code / Code Unique”).

Improvement

Introduce explicit dataset role semantics:

dataset_role = authority | customer
OR a flag such as --authority IFRA



Result

No more Excel adapters for authority runs
No fake customer codes
Tools become semantics‑aware instead of schema‑fragile

✅ Status: Not implemented yet; clearly identified, low‑risk future change.

2. Allow CAS_Structurer to Run Without a True Customer Code (Authority Mode)
Agreed behavior
When dataset_role == authority:

customer_id may still exist (e.g. "IFRA") for provenance
Customer code is optional
CAS acts as the only upstream identifier

Concrete change

In authority mode:

auto‑derive Customer Code / Code Unique = CAS
or drop customer code from deduplication subset


Dedup keys switch from:
Plain Text(customer_id, customer_code, CAS)Show more lines
to:
Plain Text(CAS)Show more lines


Why this matters

IFRA is not conceptually a customer
Authority data should not carry customer artifacts
Removes structural hacks upstream

✅ Status: Identified clearly; planned for later.

3. Formalize Dual Identity in DB1 (Canonical DB)
You made an important and precise constraint:

Dual identity in DB1 is allowed only when SMILES exists and InChI/InChIKey does not.

This should be codified explicitly.
Proposed DB1 identity rules






























SituationAllowed?ActionInChIKey present✅Use as canonical identitySMILES present, no InChIKey✅Generate InChI + InChIKey inside DB1SMILES only (upstream)✅Allowed before DB1No SMILES, no InChIKey❌Reject
Key principle

SMILES is a valid functional identity
InChIKey is the required canonical identity
DB1 is the only component allowed to mint canonical identities

✅ Status: Conceptually agreed; implementation deferred.

4. Use SMILES as a Fallback Identifier Only for Computation / Staging
You correctly observed:

“Using SMILES as a backup identifier is reasonable for most parameters.”

This is true — but only in defined scopes.
Where SMILES fallback is explicitly acceptable

Phys/chem property calculation
Temporary deduplication during staging
GS and other reference‑only sources
CASResolver output when InChIKey is missing

Where it must not be used

DB1 persistence
Long‑term identity
Cross‑dataset reconciliation
Regulatory-facing exports

Improvement

Explicitly distinguish:

functional_identity = canonical_smiles
canonical_identity = inchikey



✅ Status: Agreed direction; needs formalization in Canonical_DB.

5. Centralize Identity Normalization in Canonical_DB
Current risk

InChIKey generation happens implicitly or upstream (or not at all)
Identity logic is scattered across tools

Improvement

Add a single guard at DB1 ingest:

If SMILES exists and InChIKey is missing → generate deterministically
Log provenance (generated_from_smiles)


Upstream tools remain lightweight and permissive

Result

DB1 becomes self-healing
No silent identity fragmentation
Clear audit trail

✅ Status: Not yet implemented; deemed high‑value, low complexity.

6. Keep GS as Reference‑Only and Compatible with This Model
Your GS conclusions align perfectly with the above:

GS may contribute SMILES
GS never mints identities
GS data only crosses into DB1 after explicit decision
The dual‑identity model safely supports this

✅ Status: Policy decided and documented.

7. Pipeline Hygiene: Preserve Current Workarounds, Don’t Cement Them
Short‑term workaround (Excel adapter) was:

Correct
Explicit
Transparent
Non‑destructive

Long‑term improvement:

Remove adapter once authority mode exists
Upgrade pipeline runner to pass dataset role instead of assuming customer

✅ Status: Workaround accepted for this run only; improvement queued.

Summary (One‑Paragraph Takeaway)
You’ve identified two architectural refinements worth making later:

Authority‑aware CAS_Structurer / pipeline behavior (no forced customer code).
Explicit dual‑identity handling in DB1, where SMILES is allowed as a temporary functional identity, but InChIKey is mandatory before canonical persistence, and may be generated centrally if absent.

Neither blocks the current IFRA run. Both improve correctness, clarity, and long‑term robustness. The fact that they surfaced organically during a real run is a strong signal of healthy system evolution — not a flaw.
When you’re ready to pick these up again, they can be tackled independently, with small, controlled changes.
If you’d like next time, I can:

turn these into a short design doc,
help you scope the exact DB1 changes,
or sketch the minimal diff for CAS_Structurer authority mode.