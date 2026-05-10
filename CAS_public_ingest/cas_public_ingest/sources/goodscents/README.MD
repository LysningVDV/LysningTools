

✅ Summary: Good Scents Discovery & Evaluation
Good Scents is retained as a reference‑only source for descriptive and legacy CAS information, and is not used to expand or redefine the authoritative material palette.

Objective
Evaluate whether The Good Scents Company database meaningfully expands the chemical material palette beyond IFRA, and whether it should be treated as a source of new materials or as a reference‑only enrichment source.

Method (what was actually done)


CAS‑first enrichment

Checked which IFRA materials had GS reference pages.
Confirmed GS is well aligned with IFRA at the conceptual level.



Controlled GS discovery

Implemented bounded, anchor‑based crawling of GS rw_id pages.
Avoided keyword search and brute‑force enumeration due to sparsity.
Explored a high‑density GS island around rw1375541.



Entity‑level consolidation

Collapsed raw GS discovery output (64 CAS rows) into GS entities keyed by rw_id.
Explicitly handled multi‑CAS pages (stereo families, reaction products).
Filtered weak names (alpha, beta, numeric codes).
Introduced explicit IFRA shadow detection (CAS + name‑based).




Key Results (facts, not interpretation)

29 GS entities identified after consolidation.
Distribution:

~26 multi‑CAS stereo families or reaction products
3–4 single‑CAS monomers


The vast majority of entities:

Represent CAS fragmentation, not new chemistry
Are conceptually covered by IFRA, even when CAS differ


No evidence of:

missing IFRA odorant classes
novel GS‑only chemical archetypes
large backlogs of materially relevant substances absent from IFRA




Conclusion

Good Scents does not meaningfully expand the authoritative material palette beyond IFRA.

Its value lies in:

reference context
legacy CAS coverage
isomer / reaction‑product visibility
descriptive support

—not in introducing new core materials.
This conclusion is data‑driven, based on structured discovery, consolidation, and shadow‑detection—not assumption.

Decision
✅ Freeze GS discovery at this point
✅ Retain GS as a reference‑only data source
❌ Do not promote GS entities automatically into DB2
❌ Do not run GS discovery routinely in pipelines
GS discovery remains available as a bounded, reusable tool, but is not considered a growth driver.

📌 System / Architecture Note (ready to paste)
You can paste the following verbatim into your system documentation.

Good Scents (GS) – Data Source Policy
Status: Reference‑only
Authority Level: Non‑authoritative (supporting source)
Summary
The Good Scents Company database was evaluated as a potential source of additional chemical materials beyond IFRA. A structured, anchor‑based discovery and consolidation process was implemented and executed.
Findings

GS material pages predominantly represent:

stereo‑isomer families
reaction products
legacy / alternative CAS registrations


After entity‑level consolidation, very few GS‑only monomeric materials remained.
No evidence was found for significant IFRA‑missing chemical archetypes.
Most GS entities are conceptually equivalent to existing IFRA materials.

Policy

GS is retained as a reference enrichment source only.
GS data may be used for:

descriptive context
legacy CAS resolution
research support


GS data must not drive automatic material promotion or palette expansion.
Any GS‑derived material considered for inclusion must undergo explicit manual review.

Rationale
This policy is based on empirical discovery results and governance principles prioritizing:

material‑level authority
avoidance of CAS‑driven over‑expansion
auditability and traceability

Date of evaluation: 2026‑05
Conclusion: GS does not materially expand the authoritative material space beyond IFRA.

✅ Addendum: Permitted Future Use of Good Scents (GS)
Scope clarification
Although GS is not treated as a source of new authoritative materials, it may still be consulted in the future for CAS‑level reference lookups, including but not limited to:

physical or descriptive material properties
(e.g. density, odor descriptors, boiling point where available)
historical or alternative CAS registrations
legacy naming variants and context
qualitative notes useful for expert interpretation

Constraints
Any such use must satisfy all of the following:

✅ GS remains a non‑authoritative reference
✅ GS data is used only after CAS identity is established elsewhere (e.g. IFRA, DB2)
✅ GS information must be clearly labeled as “reference / descriptive”
❌ GS properties must not override canonical data sources
❌ GS lookups must not imply regulatory or material endorsement

Rationale
This preserves GS’s value as a supporting knowledge base, while maintaining:

material‑level authority with IFRA and canonical databases
clear provenance of properties versus identity
auditability of enrichment decisions

In short:

GS is suitable for “tell me more about this CAS,”
not for “tell me what CAS exist.”