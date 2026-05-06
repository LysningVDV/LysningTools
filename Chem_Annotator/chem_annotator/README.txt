# Chem Annotator (chem_annotator)

Chem Annotator converts SMILES strings into a stable, schema-complete set of functional-group and motif descriptors (feature counts) suitable for data pipelines and modeling workflows. [4](https://lysninginnovationconsultant-my.sharepoint.com/personal/villeneuve_lysning_nl/Documents/Microsoft%20Copilot%20Chat%20Files/unsaturations.py)[1](https://lysninginnovationconsultant-my.sharepoint.com/personal/villeneuve_lysning_nl/Documents/Microsoft%20Copilot%20Chat%20Files/macrocyclic.py)

Key guarantees:
- **Stable schema:** the output contains a fixed set of keys/columns across valid and invalid inputs. [1](https://lysninginnovationconsultant-my.sharepoint.com/personal/villeneuve_lysning_nl/Documents/Microsoft%20Copilot%20Chat%20Files/macrocyclic.py)[4](https://lysninginnovationconsultant-my.sharepoint.com/personal/villeneuve_lysning_nl/Documents/Microsoft%20Copilot%20Chat%20Files/unsaturations.py)
- **Robust invalid handling:** invalid SMILES return the full schema with numeric fields `0`, string fields `""`, and `"Valid": 0`. [1](https://lysninginnovationconsultant-my.sharepoint.com/personal/villeneuve_lysning_nl/Documents/Microsoft%20Copilot%20Chat%20Files/macrocyclic.py)[4](https://lysninginnovationconsultant-my.sharepoint.com/personal/villeneuve_lysning_nl/Documents/Microsoft%20Copilot%20Chat%20Files/unsaturations.py)
- **Deterministic dot-SMILES policy:** multi-fragment SMILES (with `.`) are normalized to a single “main” fragment using a documented selection policy. [2](https://lysninginnovationconsultant-my.sharepoint.com/personal/villeneuve_lysning_nl/Documents/Microsoft%20Copilot%20Chat%20Files/malonates.py)[1](https://lysninginnovationconsultant-my.sharepoint.com/personal/villeneuve_lysning_nl/Documents/Microsoft%20Copilot%20Chat%20Files/macrocyclic.py)
- **Optional schema version stamp:** a `SchemaVersion` field can be present for governance and compatibility tracking. [1](https://lysninginnovationconsultant-my.sharepoint.com/personal/villeneuve_lysning_nl/Documents/Microsoft%20Copilot%20Chat%20Files/macrocyclic.py)[1](https://lysninginnovationconsultant-my.sharepoint.com/personal/villeneuve_lysning_nl/Documents/Microsoft%20Copilot%20Chat%20Files/macrocyclic.py)

---

## Installation

This project uses RDKit and standard Python packaging.

```bash
pip install .

✅ README.md (customer‑facing, complete version)
Markdown# Chem AnnotatorChem Annotator converts SMILES strings into a comprehensive, stable set of chemical descriptors based on curated RDKit SMARTS logic and domain-specific functional group rules. Outputs are designed to be **schema-stable**, **machine‑learning‑ready**, and **robust to invalid inputs**.---# 1. Installation (Conda Recommended)Chem Annotator depends on RDKit.  The recommended setup is:```bashconda create -n chem-annotator python=3.11 rdkit -c conda-forgeconda activate chem-annotatorpip install .Show more lines
This ensures RDKit and Python dependencies resolve correctly.

2. Quick Start
Single SMILES
Pythonfrom chem_annotator.aggregator import features_for_smilesfeats = features_for_smiles("CCO", include_schema_version=True)print(feats["Valid"])              # 1print(feats["TotalAlcoholCount"])  # 1 (ethanol)print(feats["SchemaVersion"])      # "1" (optional)Show more lines
Invalid SMILES:
Pythonfeats = features_for_smiles("NOT_A_SMILES")assert feats["Valid"] == 0# All numeric fields = 0, string fields = ""Show more lines
This follows the robustness rule enforced by the integration tests. [lysninginn...epoint.com]

3. Batch Processing
Pythonimport pandas as pdfrom chem_annotator.io_utils import process_dataframedf = pd.DataFrame([    {"CAS_ID": "A", "SMILES": "CCO"},    {"CAS_ID": "B", "SMILES": "NOT_A_SMILES"},    {"CAS_ID": "C", "SMILES": None},    {"CAS_ID": "D", "SMILES": "CCO.[Na+]"},])out_df, invalid_report, empty_report = process_dataframe(df)Show more lines
Batch behavior:

Every row in out_df contains the full schema
invalid_report contains rows where RDKit parsing fails (“Failed to parse”)
empty_report contains rows that became empty after cleaning (“Empty after cleaning”)
 [lysninginn...epoint.com]


4. SMILES Cleaning & Dot‑SMILES Policy
Before parsing, Chem Annotator normalizes SMILES:

Converts None/NaN → ""
Unescapes HTML entities
Replaces NBSP
Removes ASCII control characters
Treats "" or "nbsp" as empty
 [lysninginn...epoint.com]

Dot‑SMILES (multi‑fragment) resolution
For SMILES containing ".":

Split fragments
Prefer fragments containing carbon
Break ties using heavy‑atom count
If none parse: choose the longest fragment string
Ignore empty fragments (e.g. "..CCO.." → "CCO")
 [lysninginn...epoint.com], [lysninginn...epoint.com]

Example:
"CCO.[Na+]" → "CCO"

5. Robustness Guarantees
Chem Annotator always returns a complete schema:

For valid SMILES: all descriptors filled
For invalid SMILES or empty‑after‑clean:

Valid = 0
Numeric fields = 0
String fields = ""
All schema keys present
✔ Guaranteed by integration tests
 [lysninginn...epoint.com]



This ensures downstream systems receive a predictable, rectangular dataset.

6. Schema Versioning
The schema includes:

SchemaVersion: empty ("") by default
If include_schema_version=True, valid SMILES include "1" (or configured version)
 [lysninginn...epoint.com]

Invalid SMILES always return SchemaVersion = "" to comply with the robustness rule.

7. Feature Semantics (Customer Definitions)
Chem Annotator produces a wide range of descriptors.
Below are the key semantics from the underlying feature modules.
7.1 Unsaturations
Based on unsaturations.py
 [lysninginn...epoint.com]

NumUnsaturatedBonds

Counts strict C–C unsaturation
Aromatic C–C = 1
Excludes heteroatom unsaturation


NumUnsaturatedBonds_All

Legacy count including C=O, N=O, aromatic, etc.



7.2 Halogens & Halophenols
Based on halogens.py
 [lysninginn...epoint.com]

Halogen atom counts (HalogenAtomCount_*)
Halogenated carbon counts (aryl vs alkyl)
Halophenol = phenolic OH site on an aromatic ring bearing ≥1 halogen
Per‑halogen subtype fields allow marker-style overlap
(one OH site may increment multiple buckets)

7.3 Macrocyclic Musks
Based on macrocyclic.py
 [lysninginn...epoint.com]

Macro rings: ≥12 atoms
Ketone: in‑ring carbonyl carbon that is not ester‑like
Lactone: C(=O)O with both atoms inside the macro ring
Output: (MacroMusks_Total, MacroMusks_Ketones, MacroMusks_Lactones)

7.4 Malonates
Based on malonates.py
 [lysninginn...epoint.com]

Detects CH(R)(COOX)(COOX′) centers
Side types:

"ester" = OR
"acid" = neutral carboxylic acid (–C(=O)OH)


Carboxylates (–C(=O)O⁻) are not "acid"
Outputs: diester, half‑ester, diacid, total malonate-like centers


8. Full Schema Key List
Derived from schema.py and module-level expansions
(including aldehyde subkeys, halogen subtype keys, and audit fields). [lysninginn...epoint.com]
Below is the complete list as of Schema Version "1"
(grouped for readability — your actual output DataFrames contain these as columns):
Core validity & metadata

Valid
SchemaVersion

Alcohols & Polyols

TotalAlcoholCount
PrimaryAlcoholCount
SecondaryAlcoholCount
TertiaryAlcoholCount
PhenolCount
AlphaHydroxyCarbonylCount
EnolicOHCount
OximeCount
AllylicAlcoholCount
BenzylicAlcoholCount
PropargylicAlcoholCount
HemiacetalCount
HemiketalCount
Vicinal12DiolCount
OneThreeDiolCount
IsPolyol
AlcoholAudit (string)

Aldehydes (from classify_aldehyde template)
Keys include, depending on module:

AldehydeCount
AldehydeCount_NoAlphaBetaSub
AlphaBetaUnsaturatedAldehydeCount
ArylAldehydeCount
CyclicAliphaticAldehydeCount
CyclicAldehyde_BetaSubCount_0
CyclicAldehyde_BetaSubCount_1
CyclicAldehyde_BetaSubCount_2
... (any other template keys generated by classify_aldehyde)
AldehydeAudit (string) [lysninginn...epoint.com]

Ethers / Carbonyl / Esters

EtherCount (legacy)
EtherCount_Total
EtherCount_Acyclic
EtherCount_Cyclic
EpoxideCount
EtherAliphaticCount
EtherAromaticCount
EtherMixedCount
EtherRingCount
KetoneCount
EsterCount_Total
EsterCount_Open
LactoneCount
CarboxylicAcidCount
CarboxylicAcidCount_Fragment

Sulfur Family

ThiolCount
ThiophenolCount
AliphaticThiolCount
DisulfideCount
ThioesterCount
ThioetherCount
SulfoxideCount
SulfoneCount
Thiophenol_OrthoCount
Thiophenol_MetaCount
Thiophenol_ParaCount

Malonates

MalonateLikeCount
MalonateDiesterCount
MalonateHalfEsterCount
MalonicAcidCount
 [lysninginn...epoint.com]

Halogens

HalogenatedPhenolCount
HalogenatedCarbonCount
HalogenAtomCount_Total
For each halogen type F/Cl/Br/I:

HalogenAtomCount_{X}
HalogenatedCarbonCount_{X}
HalogenatedArylCarbonCount_{X}
HalogenatedAlkylCarbonCount_{X}
HalogenatedPhenolCount_{X}
 [lysninginn...epoint.com]



Aromatics / Heterocycles

PyridineCount
ThiazoleCount
TerpeneLikeUnitCount

Nitro & Nitriles

NitroGroupCount
NitrileCount
NitrileFragmentCount

Macrocyclic Musks

MacroMusks_Total
MacroMusks_Ketones
MacroMusks_Lactones
 [lysninginn...epoint.com]

Amines

AmineCount_Total
AmineCount_Primary
AmineCount_Secondary
AmineCount_Tertiary

Rings & Unsaturation

NumAromaticAtoms
NumAromaticRings
NumAliphaticRings
NumRingsTotal
NumUnsaturatedBonds (strict C–C)
NumUnsaturatedBonds_All (legacy)
IsFullySaturated

Atom Totals

TotalNitrogenAtomCount
TotalSulfurAtomCount
TotalSulfurGroupCount
TotalNitrogenGroupCount

High-Impact Odorant Tiers

HighImpactTier1Count
HighImpactTier2Count
HighImpactSummary (string)


9. Testing
Run the full test suite:
Shellpytest -qShow more lines
The suite includes:

Functional-group unit tests
Integration tests (schema completeness & invalid behavior)
Regression tests using a curated, minimal dataset
End-to-end pipeline smoke tests


10. Support
For integration help or schema updates, contact the maintainers.