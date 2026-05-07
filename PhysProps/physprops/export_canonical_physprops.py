import logging
import pandas as pd
from physprops.io.excel_io import write_xlsx_atomic
from physprops.canonical.builder import build_canonical_dataframe

logger = logging.getLogger(__name__)

# Path to your wide output Excel file
wide_excel_path = "output_cas_results.xlsx"

# Path to save canonical table
canonical_excel_path = "canonical_physprops.xlsx"

# Path to save audit log
audit_excel_path = "canonical_physprops_audit.xlsx"

# Load wide output
df_wide = pd.read_excel(wide_excel_path, engine="openpyxl")

# Build canonical and audit tables
canonical_df, audit_df = build_canonical_dataframe(df_wide, strict_schema=True)

# Save canonical table
write_xlsx_atomic(canonical_df, canonical_excel_path, sheet_name="Sheet1")

# Save audit log
write_xlsx_atomic(audit_df, audit_excel_path, sheet_name="Sheet1")

logger.info("Canonical physprops table written to: %s", canonical_excel_path)
logger.info("Audit log written to: %s", audit_excel_path)