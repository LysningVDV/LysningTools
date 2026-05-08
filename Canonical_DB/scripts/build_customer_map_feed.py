from pathlib import Path
import pandas as pd

# === CONFIG ===
INPUT_XLSX = Path(r"C:\Users\vdevi\OneDrive - Lysning Innovation Consultants B.V\Lysning\Tools\Lysning_CASResolver\CAS_input_exploded_20260508T152655296486Z.xlsx")
OUT_CSV = Path(r"Canonical_DB\exports_pipeline\customer_map_feed.csv")

NEEDED = [
    "customer_id",
    "timestamp_seen_utc",
    "Customer Code / Code Unique",
    "Name",
    "CAS",
    "CAS_valid",
]

def main() -> None:
    df = pd.read_excel(INPUT_XLSX, engine="openpyxl")
    missing = [c for c in NEEDED if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {missing}. Found: {list(df.columns)}")

    out = df[NEEDED].copy()

    # Basic filtering
    out["CAS"] = out["CAS"].astype(str).str.strip()
    out = out[out["CAS"].ne("")]

    # Remove invalid rows based on status text
    out["CAS_valid"] = out["CAS_valid"].astype(str)
    out = out[~out["CAS_valid"].str.lower().str.contains("invalid")]

    # Keep latest per (customer_id, CAS)
    out = out.sort_values("timestamp_seen_utc")
    out = out.drop_duplicates(subset=["customer_id", "CAS"], keep="last")

    # Standardize names for downstream DB2 customer_map upsert
    out = out.rename(columns={"CAS": "cas_number_normalized", "CAS_valid": "cas_validity"})

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_CSV, index=False, encoding="utf-8")

    print("WROTE", OUT_CSV.resolve(), "rows", len(out))

if __name__ == "__main__":
    main()