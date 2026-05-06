# aggregator.py
# Production-ready aggregator for SMILES feature extraction.
# This module is auto-generated from features.py.

# ---------------------------------------------------------------------------
# chem_annotator/features.py
# Fully merged and perfumer-validated feature extractor
# ---------------------------------------------------------------------------

from typing import Dict, Union, List
from rdkit import Chem
from rdkit.Chem import Fragments
from rdkit.Chem import rdMolDescriptors as rdMD
from .schema import make_empty_features, SCHEMA_VERSION
from .chem_patterns import PATTS, ESTER_PATT
from .features.alcohols import (
    classify_and_count_alcohols,
    audit_alcohol_sites,
    count_diol_motifs,
)
from .features.phenols import count_alkyl_phenols
from .features.aldehydes import classify_aldehyde

from .features.unsaturations import (
    count_cc_unsaturated_bonds,
    count_cc_alkene_bonds,
    count_cc_alkyne_bonds,
)
from .features.amines import classify_and_count_amines
from .features.carbonyl import count_lactones_split
from .features.ethers import count_ethers_excluding_esters, ether_category_counts
from .features.sulfur import (
    count_thiols,
    count_aliphatic_thiols,
    count_thiophenols,
    count_disulfides,
    count_thioesters,
    count_thioethers_excluding_thioesters,
    count_sulfoxides,
    count_sulfones,
    classify_thiophenol_positions,
)

from .features.acetals import count_acetals_ketals_orthoesters

from .features.halogens import (
    count_halogenated_phenols,
    count_halogenated_phenols_by_halogen,
    count_halogenated_carbons,
    count_halogenated_carbons_by_halogen,
    count_halogenated_carbons_by_halogen_split_aromatic,
    count_halogen_atoms_total,
    count_halogen_atoms_by_halogen,
)

from .features.nitro import (
    count_nitro_groups,
    count_imines,
    count_amides,
    count_lactams,
    count_ureas,
    count_urethanes,
    count_isocyanates,
)

from .features.malonates import count_malonate_structures
from .features.macrocyclic import count_macrocyclic_musks

from .utils import (
    count_smarts,
    count_unsaturated_bonds,  # legacy, includes hetero atoms
)# ---------------------------------------------------------------------------
# MAIN FEATURE FUNCTION
# ---------------------------------------------------------------------------

def _aldehyde_template_keys() -> List[str]:
    """Get aldehyde feature keys once (classify_aldehyde returns a dict expanded into the schema)."""
    try:
        tm = Chem.MolFromSmiles("CC=O")  # acetaldehyde; should always parse
        if tm is None:
            return []
        al_counts, _audit = classify_aldehyde(tm)
        return list(al_counts.keys())
    except Exception:
        return []


def _empty_features() -> Dict[str, Union[int, str]]:
    """Return a complete zero/empty schema dict for invalid SMILES rows."""
    # Delegates to centralized schema (single source of truth).
    # Copy returned dict so callers can safely mutate without affecting global defaults.
    return dict(make_empty_features())


def features_for_smiles(smi: str, include_schema_version: bool = False) -> Dict[str, Union[int, str]]:
    m = Chem.MolFromSmiles(smi)
    if m is None:
        return _empty_features()

    # Alcohols
    (
        primA, secA, tertA, phen,
        alpha_hydroxy, enol_count,
        allylicA, benzylicA, propargylicA,
        hemiacetalA, hemiketalA,
        oxime_count,
        oh_alpha_carbons
    ) = classify_and_count_alcohols(m)
    vic12, one3 = count_diol_motifs(m, oh_alpha_carbons)
    alcohol_audit = audit_alcohol_sites(m)
    total_alcohols = primA + secA + tertA + phen + alpha_hydroxy + enol_count
    acetal_count, ketal_count, orthoester_count = count_acetals_ketals_orthoesters(m)
    aryl_o_alkyl = count_smarts(m, PATTS.get("ArylOAlkylEther"))
    diaryl_ether = count_smarts(m, PATTS.get("DiarylEther"))
    alkyl_phenols = count_alkyl_phenols(m)

    # Aldehydes
    al_counts, aldehyde_audit = classify_aldehyde(m)

    # SMARTS motifs
    nitriles = count_smarts(m, PATTS.get("Nitrile"))
    try:
        nitriles_frag = Fragments.fr_nitrile(m)
    except Exception:
        nitriles_frag = None

    lactone_count, open_ester_count, esters_total = count_lactones_split(m)
    acrylates = count_smarts(m, PATTS.get("AcrylateEster"))
    methacrylates = count_smarts(m, PATTS.get("MethacrylateEster"))

    # New ether category block
    ether_cats = ether_category_counts(m)
    ethers = ether_cats["EtherCount_Total"]  # keep legacy 'EtherCount' as total
    ether_acyclic = ether_cats["EtherCount_Acyclic"]
    ether_cyclic = ether_cats["EtherCount_Cyclic"]
    epoxides = ether_cats["EpoxideCount"]

    # === Ethers subtypes ===
    ether_aliphatic = count_smarts(m, PATTS.get("Ether_Aliphatic"))
    ether_aromatic = count_smarts(m, PATTS.get("Ether_Aromatic"))
    ether_mixed = count_smarts(m, PATTS.get("Ether_Mixed"))
    ether_ring = count_smarts(m, PATTS.get("Ether_Ring"))

    ketones = count_smarts(m, PATTS.get("Ketone"))
    acids = count_smarts(m, PATTS.get("CarboxylicAcid"))
    acid_frag = Fragments.fr_COO(m)



    # Amines
    amine_primary, amine_secondary, amine_tertiary, amines_total = classify_and_count_amines(m)

    # Sulfur families
    thiols_total = count_thiols(m)
    thiophenols = count_thiophenols(m)
    aliph_thiols = count_aliphatic_thiols(m)
    disulfides = count_disulfides(m)
    thioesters = count_thioesters(m)
    thioethers = count_thioethers_excluding_thioesters(m)
    sulfoxides = count_sulfoxides(m)
    sulfones = count_sulfones(m)
    thiophenol_o, thiophenol_m, thiophenol_p = classify_thiophenol_positions(m)

    # Malonates
    malon_diester, malon_half, malon_diacid, malon_total = count_malonate_structures(m)

    # Macro musks
    macro_total, macro_ket, macro_lac = count_macrocyclic_musks(m)

    # Halogens (compute variables; DO NOT put dict key:value lines here)
    halophenols = count_halogenated_phenols(m)
    halocarbons = count_halogenated_carbons(m)
    halo_atoms_total = count_halogen_atoms_total(m)
    halo_atoms_by = count_halogen_atoms_by_halogen(m)
    halocarb_by = count_halogenated_carbons_by_halogen(m)
    halocarb_split = count_halogenated_carbons_by_halogen_split_aromatic(m)
    halophen_by = count_halogenated_phenols_by_halogen(m)

    # Nitro
    nitro_groups = count_nitro_groups(m)
    imine_count = count_imines(m)
    amide_total = count_amides(m)
    lactam_count = count_lactams(m)
    urea_count = count_ureas(m)
    urethane_count = count_urethanes(m)
    isocyanate_count = count_isocyanates(m)

    # Rings and unsaturation
    pyridines = count_smarts(m, PATTS.get("Pyridine"))
    thiazoles = count_smarts(m, PATTS.get("Thiazole"))
    indoles = count_smarts(m, PATTS.get("Indole"))
    furans = count_smarts(m, PATTS.get("Furan"))
    thiophenes = count_smarts(m, PATTS.get("Thiophene"))
    isoprenyls = count_smarts(m, PATTS.get("Isoprenyl"))

    # --- Hydrocarbon classification (pure C/H only) ---
    atom_nums = [a.GetAtomicNum() for a in m.GetAtoms()]
    carbon_count = sum(1 for z in atom_nums if z == 6)
    is_pure_hydrocarbon = 1 if all(z in (1, 6) for z in atom_nums) else 0

    has_aromatic_atoms = any(a.GetIsAromatic() for a in m.GetAtoms())
    ring_total = m.GetRingInfo().NumRings()

    is_hc_aromatic = 1 if (is_pure_hydrocarbon and has_aromatic_atoms) else 0
    is_hc_aliphatic = 1 if (is_pure_hydrocarbon and not has_aromatic_atoms) else 0
    hc_ring_count = ring_total if is_pure_hydrocarbon else 0

    is_terpene_hydrocarbon = 1 if (is_pure_hydrocarbon and isoprenyls >= 1) else 0

    num_arom_atoms = sum(1 for a in m.GetAtoms() if a.GetIsAromatic())
    num_arom_rings = rdMD.CalcNumAromaticRings(m)
    num_aliph_rings = rdMD.CalcNumAliphaticRings(m)
    num_rings_total = m.GetRingInfo().NumRings()
    num_unsat_all = count_unsaturated_bonds(m)
    num_unsat_cc = count_cc_unsaturated_bonds(m)
    num_alkenes = count_cc_alkene_bonds(m)
    num_alkynes = count_cc_alkyne_bonds(m)
    fully_saturated = 1 if num_unsat_cc == 0 else 0

    # Atom-level totals (not functional group counts)
    total_n_atoms = sum(1 for a in m.GetAtoms() if a.GetAtomicNum() == 7)
    total_s_atoms = sum(1 for a in m.GetAtoms() if a.GetAtomicNum() == 16)

    # -----------------------------------------------------------------------
    # HIGH-IMPACT ODORANT TIERS (Final perfumery logic)
    # -----------------------------------------------------------------------
    # Tier 1: ultra-potent trace-level
    high_tier1 = (
        thiophenols +
        aliph_thiols +
        disulfides +
        sulfoxides +
        sulfones +
        halophenols +
        halocarbons +
        nitro_groups +
        al_counts["AlphaBetaUnsaturatedAldehydeCount"]
    )

    # Tier 2: strong diffusive but not trace-potent
    high_tier2 = (
        enol_count +  # enols
        thioethers +  # mild sulfur
        malon_total +  # malonates
        al_counts["AldehydeCount_AlphaSubstituted"] +
        al_counts["AldehydeCount_BetaSubstituted"] +
        phen +  # phenols (total)
        thiophenol_o + thiophenol_m + thiophenol_p +  # positional thiophenols
        nitriles  # nitriles are impactful but not Tier 1
    )

    # -----------------------------------------------------------------------
    # RETURN COMPLETE FEATURE DICT
    # -----------------------------------------------------------------------
    return {
        "Valid": 1,
        "SchemaVersion": SCHEMA_VERSION if include_schema_version else "",
        
        # === Alcohols ===
        "TotalAlcoholCount": total_alcohols,
        "PrimaryAlcoholCount": primA,
        "SecondaryAlcoholCount": secA,
        "TertiaryAlcoholCount": tertA,
        "PhenolCount": phen,
        "AlphaHydroxyCarbonylCount": alpha_hydroxy,
        "EnolicOHCount": enol_count,
        "OximeCount": oxime_count,
        "AllylicAlcoholCount": allylicA,
        "BenzylicAlcoholCount": benzylicA,
        "PropargylicAlcoholCount": propargylicA,
        "AcetalCount": acetal_count,
        "KetalCount": ketal_count,
        "OrthoesterCount": orthoester_count,
        "HemiacetalCount": hemiacetalA,
        "HemiketalCount": hemiketalA,
        "Vicinal12DiolCount": vic12,
        "OneThreeDiolCount": one3,
        "IsPolyol": 1 if total_alcohols >= 2 else 0,
        "AlcoholAudit": alcohol_audit,

        # === Aldehydes (detailed) ===
        "AldehydeAudit": aldehyde_audit,
        **al_counts,

        # === Ethers / Carbonyls / Esters ===
        "EtherCount": ethers,  # legacy name (kept): equals EtherCount_Total
        "EtherCount_Total": ethers,
        "EtherCount_Acyclic": ether_acyclic,
        "EtherCount_Cyclic": ether_cyclic,
        "EpoxideCount": epoxides,
        "EtherAliphaticCount": ether_aliphatic,
        "EtherAromaticCount": ether_aromatic,
        "EtherMixedCount": ether_mixed,
        "EtherRingCount": ether_ring,
        "KetoneCount": ketones,
        "EsterCount_Total": esters_total,
        "EsterCount_Open": open_ester_count,
        "LactoneCount": lactone_count,
        "AcrylateEsterCount": acrylates,
        "MethacrylateEsterCount": methacrylates,
        "CarboxylicAcidCount": acids,
        "CarboxylicAcidCount_Fragment": acid_frag,


        # === Sulfur ===
        "ThiolCount": thiols_total,
        "ThiophenolCount": thiophenols,
        "AliphaticThiolCount": aliph_thiols,
        "DisulfideCount": disulfides,
        "ThioesterCount": thioesters,
        "ThioetherCount": thioethers,
        "SulfoxideCount": sulfoxides,
        "SulfoneCount": sulfones,
        "Thiophenol_OrthoCount": thiophenol_o,
        "Thiophenol_MetaCount": thiophenol_m,
        "Thiophenol_ParaCount": thiophenol_p,

        # === Malonates ===
        "MalonateLikeCount": malon_total,
        "MalonateDiesterCount": malon_diester,
        "MalonateHalfEsterCount": malon_half,
        "MalonicAcidCount": malon_diacid,

        # === Halogens ===
        "HalogenatedPhenolCount": halophenols,
        "HalogenatedCarbonCount": halocarbons,
        "HalogenAtomCount_Total": halo_atoms_total,
        **halo_atoms_by,
        **halocarb_by,
        **halocarb_split,
        **halophen_by,

        # === Aromatics / heterocycles ===
        "PyridineCount": pyridines,
        "ThiazoleCount": thiazoles,
        "IndoleCount": indoles,
        "FuranCount": furans,
        "ThiopheneCount": thiophenes,
        "TerpeneLikeUnitCount": isoprenyls,
        "IsPureHydrocarbon": is_pure_hydrocarbon,
        "CarbonAtomCount": carbon_count,
        "IsHydrocarbonAromatic": is_hc_aromatic,
        "IsHydrocarbonAliphatic": is_hc_aliphatic,
        "HydrocarbonRingCount": hc_ring_count,
        "IsTerpeneHydrocarbon": is_terpene_hydrocarbon,
        "ArylOAlkylEtherCount": aryl_o_alkyl,
        "DiarylEtherCount": diaryl_ether,
        "AlkylPhenolCount": alkyl_phenols,

        # === Nitro ===
        "NitroGroupCount": nitro_groups,
        "ImineCount": imine_count,
        "AmideCount_Total": amide_total,
        "LactamCount": lactam_count,
        "UreaCount": urea_count,
        "UrethaneCount": urethane_count,
        "IsocyanateCount": isocyanate_count,

        # === Nitriles ===
        "NitrileCount": nitriles,
        "NitrileFragmentCount": nitriles_frag,

        # === Macro musks ===
        "MacroMusks_Total": macro_total,
        "MacroMusks_Ketones": macro_ket,
        "MacroMusks_Lactones": macro_lac,

        # === Amines ===
        "AmineCount_Total": amines_total,
        "AmineCount_Primary": amine_primary,
        "AmineCount_Secondary": amine_secondary,
        "AmineCount_Tertiary": amine_tertiary,

        # === Rings & unsaturation ===
        "NumAromaticAtoms": num_arom_atoms,
        "NumAromaticRings": num_arom_rings,
        "NumAliphaticRings": num_aliph_rings,
        "NumRingsTotal": num_rings_total,
        "NumUnsaturatedBonds": num_unsat_cc,       # strict C–C
        "NumAlkeneBonds": num_alkenes,
        "NumAlkyneBonds": num_alkynes,
        "NumUnsaturatedBonds_All": num_unsat_all,  # legacy
        "IsFullySaturated": fully_saturated,

        # === Totals for S and N ===
        "TotalNitrogenAtomCount": total_n_atoms,
        "TotalSulfurAtomCount": total_s_atoms,
        "TotalSulfurGroupCount": (
            thiols_total + thiophenols + aliph_thiols +
            disulfides + thioesters + thioethers +
            sulfoxides + sulfones
        ),
        "TotalNitrogenGroupCount": (
            amines_total + nitriles + nitro_groups +
            pyridines + thiazoles
        ),

        # === High-impact tiers ===
        "HighImpactTier1Count": high_tier1,
        "HighImpactTier2Count": high_tier2,
        "HighImpactSummary": f"T1:{high_tier1}; T2:{high_tier2}",
    }