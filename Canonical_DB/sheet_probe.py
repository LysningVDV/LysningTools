import pandas as pd

file = "canonical_physchemprops.xlsx"
book = pd.read_excel(file, sheet_name=None, engine="openpyxl")

print("SHEETS:", list(book.keys()))
for name, df in book.items():
    cols = [str(c).strip() for c in df.columns]
    print(name, "rows", len(df), "cols", len(cols), "has_exp", "experimental_henry_constant_mol_m3_pa" in cols)