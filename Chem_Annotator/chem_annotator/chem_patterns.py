from typing import Dict
from rdkit import Chem

"""Module defining SMARTS patterns for chemical functional groups and motifs."""

# ----------- Policy toggles (central place) -----------
# Enable or disable counting contexts. These flags can be imported elsewhere in the package.
EXCLUDE_ALPHA_HYDROXY_CARBONYLS: bool = True  # exclude HO–C*–C(=O)X from classic counts
TRACK_EXCLUDED_IN_AUDIT: bool = True          # show excluded sites in AlcoholAudit


# Strict IUPAC:
COUNT_ENOLS_AS_ALCOHOLS = False
EXCLUDE_ENOLS = False  # keep enols counted as EnolicOHCount


# ----------- SMARTS definitions -----------
# We define all patterns as plain strings. They are parsed at module import time into RDKit Mol objects.
# Storing only strings here avoids parsing errors at definition time. Users should not modify PATTS directly.
SMARTS: Dict[str, str] = {
    # Carbonyl families (specific, unambiguous)
    'Aldehyde':        '[CX3H1](=O)[#6]',          # Primary aldehyde: CHO attached to carbon
    'Ketone':          '[#6][CX3](=O)[#6]',        # R–CO–R'
    'Ester':           '[#6][CX3](=O)[OX2H0][#6]', # R–CO–O–R'
    'CarboxylicAcid':  '[CX3](=O)[OX2H1]',         # COOH

    # Ester subtypes: acrylates / methacrylates (polymer and reactive screening)
    "AcrylateEster": r"[CH2]=[CH]C(=O)O[#6]",          # CH2=CH–C(=O)O–R (unsubstituted)
    "MethacrylateEster": r"C=C(C)C(=O)O[#6]",          # CH2=C(CH3)–C(=O)O–R

    # === Ethers ===
    # Generic ether (R–O–R'): oxygen single-bonded to two carbons; exclude ester/carbonyl-adjacent O.
    'Ether': r'[O;D2]([#6;!$(C=O)])([#6;!$(C=O)])',
    # Aliphatic–aliphatic ether: attached to two sp3 carbons, not in a ring
    'Ether_Aliphatic': '[O;D2;!R]([CX4;!R])[CX4;!R]',
    # Aromatic–aromatic ether: attached to two aromatic carbons
    'Ether_Aromatic':  '[O;D2]([c])[c]',
    # Mixed ether: attached to one aromatic and one aliphatic carbon
    'Ether_Mixed':     '[O;D2]([c])[CX4;!R]',
    # Cyclic ether: oxygen in a ring
    'Ether_Ring':      '[O;D2;R]',

    # Nitrile
    'Nitrile':         '[CX2]#N',

    # Heteroaromatic motifs
    'Pyridine':        'n1ccccc1',
    'Thiazole':        'c1nccs1',
    "Indole": "c1ccc2[nH,n]ccc2c1",
    "Furan": "o1cccc1",
    "Thiophene": "s1cccc1",
    
    # Perfumery class markers: aryl ethers
    "ArylOAlkylEther": r"[O;D2]([c])([CX4;!a])",  # Ar–O–alkyl (sp3 C)
    "DiarylEther": r"[O;D2]([c])([c])",            # Ar–O–Ar

    # Heuristic isoprenyl motif. Useful screen for terpene-like features.
    'Isoprenyl': 'C=C(C)C',

    # Alcohol OH finder: true OH bound to aliphatic or aromatic carbon
    'OH': r'[OX2H]-[C,c;!$(C=O)]',
}


# ----------- Parsing patterns into RDKit objects -----------
# Use a safe builder that reports parse failures without crashing. PATTS is a mapping from name to Mol.
PATTS: Dict[str, Chem.Mol] = {}
for name, smarts in SMARTS.items():
    try:
        patt = Chem.MolFromSmarts(smarts)
        if patt is None:
            raise ValueError(f'Pattern for {name} did not parse: {smarts!r}')
        PATTS[name] = patt
    except Exception as e:
        # Report errors but do not fail import. The entry is omitted from PATTS.
        print(f'Warning: could not parse SMARTS for {name}: {e}')

# Additional prespecified patterns. We populate these only if the corresponding SMARTS parsed successfully.
ESTER_PATT = PATTS.get('Ester')
# Alcohol OH finder: true OH bound to aliphatic or aromatic carbon
OH_PATT = PATTS.get('OH')

