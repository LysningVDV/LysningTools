"""
Scan chem_annotator/features for ANY suspicious SMARTS, including:
- Reaction SMARTS
- Broken constructs
- Typos like $([NX3=O)_100]
"""

import pkgutil, inspect
import chem_annotator

print("\n--- SCANNING SMARTS IN chem_annotator/features ---\n")

target_strings = ["$(", "_100", "NX3", "$["]

for module in pkgutil.walk_packages(
        chem_annotator.features.__path__,
        prefix="chem_annotator.features."):
    try:
        m = __import__(module.name, fromlist=["dummy"])
        source = inspect.getsource(m)
    except Exception:
        continue

    for lineno, line in enumerate(source.splitlines(), 1):
        # Check if the line contains suspicious substrings
        if any(tok in line for tok in target_strings):
            print("⚠ POSSIBLE BROKEN SMARTS DETECTED")
            print(f"  Module: {module.name}")
            print(f"  Line {lineno}: {line.strip()}\n")

print("\n--- DONE ---\n")