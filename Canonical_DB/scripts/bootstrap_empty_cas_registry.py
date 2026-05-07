from pathlib import Path
import os
import pandas as pd

from canonical_common.cas_registry import (
    load_or_init_allowlist,
    write_registry_excel_atomic,
    get_db2_local_paths,
)

def main():
    root = os.environ.get("CANONICAL_DB_LOCAL_ROOT")
    if not root:
        raise EnvironmentError("CANONICAL_DB_LOCAL_ROOT not set")

    schema = Path("Canonical_DB") / "cas_registry_schema.json"
    allowlist = load_or_init_allowlist(schema)

    paths = get_db2_local_paths()
    empty = pd.DataFrame(columns=allowlist)

    write_registry_excel_atomic(paths["xlsx"], empty)
    print(f"Created empty DB2 registry at: {paths['xlsx']}")

if __name__ == "__main__":
    main()
