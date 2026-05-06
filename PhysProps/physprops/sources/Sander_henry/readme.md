physprops/sources/sander_henry — Sander Henry’s Law Constants Integration
Overview
This folder contains the integration of the Sander Henry’s law constants compilation (henrys-law.org) into the physprops pipeline. The compilation is a curated collection of Henry’s law constants for water as solvent, provided in machine-readable formats and accompanied by literature references. 2 [scirp.org]
We use the compilation to populate Henry’s constant values in the physprops output with clear provenance, keeping the data in the native units and definition used by the database (no unit conversion during ingestion/export). 2 [scirp.org]

Data definition (what we store)
Henry constant variant used (native to Sander database)
The Sander compilation uses the Henry’s law solubility constant HscpH^{cp}_sHscp​, defined as c/pc/pc/p (aqueous concentration divided by gas partial pressure) at infinite dilution. The units shown for this variant are mol·m⁻³·Pa⁻¹. 2 [scirp.org]
We store and export this quantity as-is (no reciprocal, no alternate variant conversion). 2 [scirp.org]

Source & citation
When referring to the compilation, the site requests citing the living review publication:

R. Sander (2023): Compilation of Henry’s law constants (version 5.0.0) for water as solvent, Atmos. Chem. Phys., 23, 10901–12440 (2023), doi:10.5194/acp-23-10901-2023. [scirp.org], [lysninginn...epoint.com]

The site explicitly notes that this 2023 publication replaces the older 2015 paper and asks users not to cite the old paper anymore. [scirp.org]

Downloads and storage
Official download location
The official downloads (machine-readable) are provided on the Henry’s law constants download page. [scirp.org]
Chosen artifact (Option 1)
We use the SQL archive:

henry_5.0.0_sql.zip — whole database in PostgreSQL syntax. [scirp.org]

Local folder layout (as used in this project)
physprops/sources/sander_henry/
  raw/
    henry_5.0.0_sql.zip
    henry-5.0.0.sql
  cache/
    (optional derived caches, e.g., sqlite)
  sander_henry.py
  README.md


raw/ contains the downloaded zip and the extracted .sql dump. [scirp.org]
cache/ is reserved for deterministic derived caches (recommended) to avoid re-parsing the SQL on every run.

Git hygiene
The raw database files are large and should typically not be committed. Add these to .gitignore:
physprops/sources/sander_henry/raw/*
physprops/sources/sander_henry/cache/*


What the pipeline exports
We export two columns (when populated):


Value column

experimental_henry_constant_mol_m3_pa
Stores HscpH^{cp}_sHscp​ in mol·m⁻³·Pa⁻¹ (native definition and units). 2 [scirp.org]



Source column (verbose audit format; Option 2)

source_henry_constant
Example format:

Sander Henry v5.0.0 (ACP 2023) HscpSI @298.15K; ref=3500


The string encodes:

compilation identity and version (e.g., v5.0.0) [scirp.org], [lysninginn...epoint.com]
the Henry variant identifier used by the compilation (HscpSI) 2 [scirp.org]
the reference temperature tag (@298.15K) consistent with how values are represented/parameterized in the downloadable machine-readable examples 2 [scirp.org]
the internal reference number (ref=<id>) that corresponds to the compilation’s references (the site explains reference numbers appear alongside values, with full references included in associated BibTeX in the download archives). [scirp.org]





Note: We intentionally include the temperature in the source text rather than introducing a separate temperature column, per project governance.

Version checking (warning only)
To support maintainability, the module includes a non-blocking runtime check that warns if a newer database version is available on the official download page.
What it checks

The download page lists archive names that encode the version (e.g., henry_5.0.0_sql.zip). [scirp.org]
The checker fetches the download page and searches for henry_<ver>_sql.zip, then compares the highest version found to the local pinned version. [scirp.org]

Behavior

Warning-only: it must never break offline runs or CI.
Short timeout; network failures are tolerated and result in a warning that the check was skipped.

Why this is safe

It relies on the single authoritative list of downloads published by the compilation itself. [scirp.org]


Implementation notes (determinism & auditability)

Prefer lookup by InChIKey when available (stable identifier).
CAS RN may be used as a fallback key when InChIKey is missing or not found.
If multiple values exist for one species, selection must be deterministic and auditable (e.g., rule-based selection + optionally preserving ref IDs). The compilation itself can include multiple values per species from different references. [lysninginn...epoint.com], [scirp.org]


Links

Official site: henrys-law.org
Download page (SQL archive): Henry’s law constants download
Living review (ACP 2023): Sander 2023 article page


Change log (project-local)

Pinned compilation version: 5.0.0 (local artifacts: henry_5.0.0_sql.zip, henry-5.0.0.sql). [scirp.org], [lysninginn...epoint.com]
Export policy: store native HscpH^{cp}_sHscp​ (mol·m⁻³·Pa⁻¹), export value + verbose source string including @298.15K. 2 [scirp.org]

