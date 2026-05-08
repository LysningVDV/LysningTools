PhysProps Outputs
PhysProps produces three distinct output artifacts per run, each with a clear role and well-defined location.
The tool is designed to be deterministic, audit-friendly, and safe to run both standalone and as part of a larger pipeline.
Output Types

























Output typePurposeNotesWide (governed)Canonical, frozen-schema output used for joins and canonical DB upsertAlways producedLegacyBackward-compatible output for existing workflowsProduced exactly where the user requestsTemporary / intermediateInternal, debug-friendly source used for wide exportAlways produced

1. Wide (governed) export — canonical feed
What it is

A wide, governed DataFrame with a frozen schema
Includes canonical join key inchi_key
Includes enriched physicochemical properties (e.g. HSP, Henry’s law)
Intended for canonical DB upsert and downstream joins

Where it is written
Tools/output/physprops/wide_physprops_<UTCSTAMP>.xlsx

Timestamp format
YYYYMMDDTHHMMSSZ   (UTC)

Example:
wide_physprops_20260508T083937Z.xlsx

This file is never overwritten; each run produces a new timestamped artifact.

2. Legacy export — CLI-facing output
What it is

A backward-compatible output matching historical PhysProps behavior
Column structure unchanged relative to prior versions

Where it is written


If the user provides an output path:
Shellphysprops input.xlsx output.xlsxShow more lines
→ written exactly to output.xlsx


If no output path is provided:
Tools/output/physprops/legacy_physprops_<UTCSTAMP>.xlsx



This ensures:

Full backward compatibility for existing scripts
Deterministic default behavior when running the tool standalone


3. Temporary / intermediate output — debug & traceability
What it is

A temporary Excel file written from out_wide
Used internally as the source for the governed wide export
Useful for debugging and audits

Where it is written
Tools/output/physprops/temp_physprops_<UTCSTAMP>__out_wide_source.xlsx


Canonical database behavior (unchanged)
PhysProps does not change canonical database storage locations:


Live canonical database (authoritative)
%CANONICAL_DB_LOCAL_ROOT%\canonical_physchemprops.xlsx



Governance / audit artifacts (OneDrive)
Tools/Canonical_DB/
  ├── canonical_audit_physprops.xlsx
  ├── canonical_schema.json
  ├── canonical_physchemprops.rejected_physprops.xlsx
  └── backups/
       └── canonical_physchemprops__YYYYMMDD_HHMMSS.xlsx



All canonical writes are handled atomically by shared canonical utilities.

Run manifest (logging)
Each PhysProps run emits one single manifest log line summarizing all produced artifacts and their roles.
Example (JSON, single line in logs):
PhysProps manifest: {
  "run_outputs": {
    "wide_governed": ".../Tools/output/physprops/wide_physprops_20260508T083937Z.xlsx",
    "legacy": ".../output_cas_results.xlsx",
    "temp_out_wide_source": ".../Tools/output/physprops/temp_physprops_20260508T083937Z__out_wide_source.xlsx"
  },
  "canonical": {
    "canonical_db_path": ".../AppData/Local/Lysning/Canonical_DB/canonical_physchemprops.xlsx",
    "canonical_audit_path": ".../Tools/Canonical_DB/canonical_audit_physprops.xlsx",
    "backup_path": ".../Tools/Canonical_DB/backups/..."
  }
}

This allows full traceability without scanning multiple log lines.

Summary

All tool run artifacts are centralized under Tools/output/physprops/
Canonical DB locations remain unchanged
Legacy compatibility is preserved
Outputs are deterministic, timestamped, and non-overwriting
A single manifest line provides audit‑grade visibility