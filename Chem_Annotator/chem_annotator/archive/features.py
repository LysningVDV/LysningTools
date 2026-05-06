# ---------------------------------------------------------------------------
# chem_annotator/features.py
# Fully merged and perfumer-validated feature extractor
# ---------------------------------------------------------------------------

from typing import Dict, Tuple, Union, List
from rdkit import Chem
from rdkit.Chem import Fragments
from rdkit.Chem import rdMolDescriptors as rdMD

from .chem_patterns import PATTS, ESTER_PATT
from .alcohols import (
    classify_and_count_alcohols,
    audit_alcohol_sites,
    count_diol_motifs,
)
from .aldehydes import classify_aldehyde
from .utils import (
    count_smarts,
    get_ring_sets,
    atoms_in_same_ring,
    count_unsaturated_bonds,   # legacy, includes hetero atoms
)

# ---------------------------------------------------------------------------
# UNSATURATION (strict C–C)
# ---------------------------------------------------------------------------

def count_cc_unsaturated_bonds(mol: Chem.Mol) -> int:
    """Strict carbon–carbon unsaturation count."""
    n = 0
    for b in mol.GetBonds():
        a1, a2 = b.GetBeginAtom(), b.GetEndAtom()
        if a1.GetAtomicNum() == 6 and a2.GetAtomicNum() == 6:
            if b.GetIsAromatic():
                n += 1
            elif b.GetBondType() in (Chem.BondType.DOUBLE, Chem.BondType.TRIPLE):
                n += 1
    return n


# ---------------------------------------------------------------------------
# ESTERS / LACTONES
# ---------------------------------------------------------------------------

def count_lactones_split(mol: Chem.Mol) -> Tuple[int, int, int]:
    """Return lactone_count, open_ester_count, ester_total."""
    if ESTER_PATT is None:
        return 0, 0, 0
    matches = mol.GetSubstructMatches(ESTER_PATT, uniquify=True)
    if not matches:
        return 0, 0, 0

    ringsets = get_ring_sets(mol)
    lact = 0
    for m in matches:
        acyl_c = m[1]
        alkoxy_o = m[3]
        if atoms_in_same_ring(ringsets, acyl_c, alkoxy_o):
            lact += 1
    total = len(matches)
    return lact, total - lact, total


# ---------------------------------------------------------------------------
# ETHERS
# ---------------------------------------------------------------------------

def count_ethers_excluding_esters(mol: Chem.Mol) -> int:
    """Count R–O–R' ethers, excluding ester alkoxy oxygens."""
    cnt = 0
    for o in mol.GetAtoms():
        if o.GetAtomicNum() != 8 or o.GetDegree() != 2:
            continue
        nbrs = o.GetNeighbors()
        if not all(n.GetAtomicNum() == 6 for n in nbrs):
            continue
        ester_like = False
        for c in nbrs:
            for b in c.GetBonds():
                if b.GetBondType() == Chem.BondType.DOUBLE:
                    other = b.GetOtherAtom(c)
                    if other.GetAtomicNum() == 8 and other.GetIdx() != o.GetIdx():
                        ester_like = True
                        break
            if ester_like:
                break
        if not ester_like:
            cnt += 1
    return cnt


# ---------------------------------------------------------------------------
# THIOLS, DISULFIDES, THIOESTERS, THIOETHERS, SULFOXIDES, SULFONES
# ---------------------------------------------------------------------------

def count_thiols(mol: Chem.Mol) -> int:
    """Count S–H attached to carbon."""
    n = 0
    for s in mol.GetAtoms():
        if s.GetAtomicNum() == 16 and s.GetTotalNumHs() >= 1:
            if any(nb.GetAtomicNum() == 6 for nb in s.GetNeighbors()):
                n += 1
    return n


def count_aliphatic_thiols(mol: Chem.Mol) -> int:
    """S–H attached to non-aromatic carbon."""
    n = 0
    for s in mol.GetAtoms():
        if s.GetAtomicNum() == 16 and s.GetTotalNumHs() >= 1:
            if any(nb.GetAtomicNum() == 6 and not nb.GetIsAromatic()
                   for nb in s.GetNeighbors()):
                n += 1
    return n


def count_thiophenols(mol: Chem.Mol) -> int:
    """S–H on an aromatic carbon."""
    n = 0
    for s in mol.GetAtoms():
        if s.GetAtomicNum() == 16 and s.GetTotalNumHs() >= 1:
            if any(nb.GetAtomicNum() == 6 and nb.GetIsAromatic()
                   for nb in s.GetNeighbors()):
                n += 1
    return n


def count_disulfides(mol: Chem.Mol) -> int:
    """R–S–S–R'."""
    cnt = 0
    for b in mol.GetBonds():
        if (b.GetBeginAtom().GetAtomicNum() == 16 and
            b.GetEndAtom().GetAtomicNum() == 16):
            cnt += 1
    return cnt


def count_thioesters(mol: Chem.Mol) -> int:
    """R–C(=O)–S–R'."""
    cnt = 0
    for c in mol.GetAtoms():
        if c.GetAtomicNum() != 6:
            continue
        # carbonyl?
        has_c_eq_o = False
        for b in c.GetBonds():
            if b.GetBondType() == Chem.BondType.DOUBLE and \
               b.GetOtherAtom(c).GetAtomicNum() == 8:
                has_c_eq_o = True
                break
        if not has_c_eq_o:
            continue
        # sulfur single-bond neighbor?
        for nb in c.GetNeighbors():
            if nb.GetAtomicNum() == 16:
                b = mol.GetBondBetweenAtoms(c.GetIdx(), nb.GetIdx())
                if b and b.GetBondType() == Chem.BondType.SINGLE and nb.GetDegree() == 2:
                    cnt += 1
                    break
    return cnt


def count_thioethers_excluding_thioesters(mol: Chem.Mol) -> int:
    """Count R–S–R', excluding thioesters."""
    cnt = 0
    for s in mol.GetAtoms():
        if s.GetAtomicNum() == 16 and s.GetDegree() == 2:
            nbrs = s.GetNeighbors()
            if all(nb.GetAtomicNum() == 6 for nb in nbrs):
                # check for thioester-like pattern
                thioester_like = False
                for c in nbrs:
                    for b in c.GetBonds():
                        if b.GetBondType() == Chem.BondType.DOUBLE and \
                           b.GetOtherAtom(c).GetAtomicNum() == 8:
                            thioester_like = True
                            break
                    if thioester_like:
                        break
                if not thioester_like:
                    cnt += 1
    return cnt


def count_sulfoxides(mol: Chem.Mol) -> int:
    patt = Chem.MolFromSmarts("S(=O)([#6])[#6]")
    return 0 if patt is None else len(mol.GetSubstructMatches(patt, uniquify=True))


def count_sulfones(mol: Chem.Mol) -> int:
    patt = Chem.MolFromSmarts("S(=O)(=O)([#6])[#6]")
    return 0 if patt is None else len(mol.GetSubstructMatches(patt, uniquify=True))


# ---------------------------------------------------------------------------
# THIOPHENOL POSITIONAL ISOMERS (o / m / p)
# ---------------------------------------------------------------------------

def classify_thiophenol_positions(mol: Chem.Mol) -> Tuple[int, int, int]:
    """Return (#ortho, #meta, #para) positional substituted thiophenols."""
    ortho = meta = para = 0
    ring_info = mol.GetRingInfo()

    for s in mol.GetAtoms():
        if s.GetAtomicNum() != 16 or s.GetTotalNumHs() < 1:
            continue

        c_ar = None
        for nb in s.GetNeighbors():
            if nb.GetAtomicNum() == 6 and nb.GetIsAromatic():
                c_ar = nb
                break
        if c_ar is None or not c_ar.IsInRing():
            continue

        ring = None
        for r in ring_info.AtomRings():
            if c_ar.GetIdx() in r:
                ring = list(r)
                break
        if ring is None:
            continue

        start = ring.index(c_ar.GetIdx())
        ordered = ring[start:] + ring[:start]
        N = len(ordered)

        def substituted(idx):
            a = mol.GetAtomWithIdx(idx)
            for nb in a.GetNeighbors():
                if nb.GetIdx() not in ring and nb.GetAtomicNum() != 1:
                    return True
            return False

        # positions
        o_pos = {ordered[(0 + 1) % N], ordered[(0 - 1) % N]}
        m_pos = {ordered[(0 + 2) % N], ordered[(0 - 2) % N]}
        p_pos = {ordered[(0 + 3) % N], ordered[(0 - 3) % N]} if N >= 6 else set()

        if any(substituted(i) for i in o_pos):
            ortho += 1
        elif any(substituted(i) for i in m_pos):
            meta += 1
        elif any(i in p_pos and substituted(i) for i in p_pos):
            para += 1

    return ortho, meta, para


# ---------------------------------------------------------------------------
# HALOGENATED PHENOLS + HALOGENATED CARBONS
# ---------------------------------------------------------------------------

def count_halogenated_phenols(mol: Chem.Mol) -> int:
    """Phenolic rings with Cl/Br/I."""
    n = 0
    ring_info = mol.GetRingInfo()
    for o in mol.GetAtoms():
        if o.GetAtomicNum() != 8:
            continue
        for nb in o.GetNeighbors():
            if nb.GetAtomicNum() == 6 and nb.GetIsAromatic() and nb.IsInRing():
                ring_atoms = set()
                for r in ring_info.AtomRings():
                    if nb.GetIdx() in r:
                        ring_atoms = set(r)
                        break
                # halogens? Cl=17, Br=35, I=53
                if any(mol.GetAtomWithIdx(idx).GetAtomicNum() in {17, 35, 53}
                       for idx in ring_atoms):
                    n += 1
                break
    return n


def count_halogenated_carbons(mol: Chem.Mol) -> int:
    """Any carbon directly bonded to Cl/Br/I."""
    cnt = 0
    HALO = {17, 35, 53}
    for c in mol.GetAtoms():
        if c.GetAtomicNum() == 6:
            if any(nb.GetAtomicNum() in HALO for nb in c.GetNeighbors()):
                cnt += 1
    return cnt


# ---------------------------------------------------------------------------
# NITRO GROUPS
# ---------------------------------------------------------------------------

def count_nitro_groups(mol: Chem.Mol) -> int:
    """Generic nitro detection."""
    patt = Chem.MolFromSmarts("$([NX3=O)]")
    return 0 if patt is None else len(mol.GetSubstructMatches(patt, uniquify=True))


# ---------------------------------------------------------------------------
# MALONATE STRUCTURES
# ---------------------------------------------------------------------------

def count_malonate_structures(mol: Chem.Mol) -> Tuple[int, int, int, int]:
    """
    Find CH(R)(COOR)(COOR') centers.
    Return (diester, half-ester, diacid, total).
    """
    diester = half = diacid = total = 0
    visited = set()

    for c in mol.GetAtoms():
        if c.GetAtomicNum() != 6:
            continue
        c_idx = c.GetIdx()

        # gather carboxyl-type neighbors
        sides = []

        for nb in c.GetNeighbors():
            if nb.GetAtomicNum() != 6: 
                continue

            b_cn = mol.GetBondBetweenAtoms(c_idx, nb.GetIdx())
            if not b_cn or b_cn.GetBondType() != Chem.BondType.SINGLE:
                continue

            # carbonyl?
            carbonyl_O = None
            for b in nb.GetBonds():
                if b.GetBondType() == Chem.BondType.DOUBLE and \
                   b.GetOtherAtom(nb).GetAtomicNum() == 8:
                    carbonyl_O = b.GetOtherAtom(nb).GetIdx()
                    break
            if carbonyl_O is None:
                continue

            # single-bond O substituent?
            o_type = None
            for nb2 in nb.GetNeighbors():
                if nb2.GetIdx() in (c_idx, carbonyl_O):
                    continue
                if nb2.GetAtomicNum() == 8:
                    b_no = mol.GetBondBetweenAtoms(nb.GetIdx(), nb2.GetIdx())
                    if b_no and b_no.GetBondType() == Chem.BondType.SINGLE:
                        if nb2.GetTotalNumHs() >= 1:
                            o_type = "acid"
                        else:
                            # OR?
                            if any(n3.GetAtomicNum() == 6 and n3.GetIdx() != nb.GetIdx()
                                   for n3 in nb2.GetNeighbors()):
                                o_type = "ester"
                        break

            if o_type is not None:
                sides.append(o_type)

        if len(sides) == 2:
            if c_idx in visited:
                continue
            visited.add(c_idx)
            total += 1
            s = tuple(sorted(sides))
            if s == ("ester", "ester"):
                diester += 1
            elif "acid" in s and "ester" in s:
                half += 1
            elif s == ("acid", "acid"):
                diacid += 1

    return diester, half, diacid, total


# ---------------------------------------------------------------------------
# MACROCYCLIC MUSKS (DETECTED BUT NOT USED IN TIERS)
# ---------------------------------------------------------------------------

def count_macrocyclic_musks(mol: Chem.Mol) -> Tuple[int, int, int]:
    """Return (macro_total, macro_ketones, macro_lactones)."""
    ri = mol.GetRingInfo()
    macro_total = macro_ket = macro_lac = 0

    atom_rings = ri.AtomRings()
    ring_sets = [set(r) for r in atom_rings if len(r) >= 12]
    if not ring_sets:
        return 0, 0, 0

    lactone_patt = Chem.MolFromSmarts("C(=O)O")

    for r in ring_sets:
        has_ket = False
        has_lac = False

        # ketones
        for b in mol.GetBonds():
            a = b.GetBeginAtom().GetIdx()
            d = b.GetEndAtom().GetIdx()
            if a in r and d in r and b.GetBondType() == Chem.BondType.DOUBLE:
                atA, atD = mol.GetAtomWithIdx(a), mol.GetAtomWithIdx(d)
                if (atA.GetAtomicNum() == 6 and atD.GetAtomicNum() == 8) or \
                   (atD.GetAtomicNum() == 6 and atA.GetAtomicNum() == 8):
                    has_ket = True
                    break

        # lactones
        if lactone_patt is not None:
            for m in mol.GetSubstructMatches(lactone_patt, uniquify=True):
                acyl_c = m[0]
                o_alk = m[2]
                if acyl_c in r and o_alk in r:
                    has_lac = True
                    break

        if has_ket or has_lac:
            macro_total += 1
            macro_ket += has_ket
            macro_lac += has_lac

    return macro_total, macro_ket, macro_lac


# ---------------------------------------------------------------------------
# MAIN FEATURE FUNCTION
# ---------------------------------------------------------------------------

def features_for_smiles(smi: str) -> Dict[str, Union[int, str]]:
    m = Chem.MolFromSmiles(smi)
    if m is None:
        return {"Valid": 0}

    # Alcohols
    (
        primA, secA, tertA, phen,
        alpha_hydroxy, enol_count,
        allylicA, benzylicA, propargylicA,
        hemiacetalA, hemiketalA,
        oh_alpha_carbons
    ) = classify_and_count_alcohols(m)

    vic12, one3 = count_diol_motifs(m, oh_alpha_carbons)
    alcohol_audit = audit_alcohol_sites(m)
    total_alcohols = primA + secA + tertA + phen + alpha_hydroxy + enol_count

    # Aldehydes
    al_counts, aldehyde_audit = classify_aldehyde(m)

    # SMARTS motifs
    nitriles = count_smarts(m, PATTS.get("Nitrile"))
    try:
        nitriles_frag = Fragments.fr_nitrile(m)
    except Exception:
        nitriles_frag = None

    lactone_count, open_ester_count, esters_total = count_lactones_split(m)
    ethers = count_ethers_excluding_esters(m)
    # === Ethers subtypes ===
    ether_aliphatic = count_smarts(m, PATTS.get("Ether_Aliphatic"))
    ether_aromatic  = count_smarts(m, PATTS.get("Ether_Aromatic"))
    ether_mixed     = count_smarts(m, PATTS.get("Ether_Mixed"))
    ether_ring      = count_smarts(m, PATTS.get("Ether_Ring"))
    ketones = count_smarts(m, PATTS.get("Ketone"))
    acids = count_smarts(m, PATTS.get("CarboxylicAcid"))
    acid_frag = Fragments.fr_COO(m)

    # Amines
    amine_primary = Fragments.fr_NH2(m)
    amine_secondary = Fragments.fr_NH1(m)
    amine_tertiary = Fragments.fr_NH0(m)
    amines_total = amine_primary + amine_secondary + amine_tertiary

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

    # Halogens
    halophenols = count_halogenated_phenols(m)
    halocarbons = count_halogenated_carbons(m)

    # Nitro
    nitro_groups = count_nitro_groups(m)

    # Rings and unsaturation
    pyridines = count_smarts(m, PATTS.get("Pyridine"))
    thiazoles = count_smarts(m, PATTS.get("Thiazole"))
    isoprenyls = count_smarts(m, PATTS.get("Isoprenyl"))
    num_arom_atoms = sum(1 for a in m.GetAtoms() if a.GetIsAromatic())
    num_arom_rings = rdMD.CalcNumAromaticRings(m)
    num_aliph_rings = rdMD.CalcNumAliphaticRings(m)
    num_rings_total = m.GetRingInfo().NumRings()
    num_unsat_all = count_unsaturated_bonds(m)
    num_unsat_cc = count_cc_unsaturated_bonds(m)
    num_alkenes = count_cc_alkene_bonds(m)
    num_alkynes = count_cc_alkyne_bonds(m)
    fully_saturated = 1 if num_unsat_cc == 0 else 0

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
        enol_count +                                  # enols
        thioethers +                                  # mild sulfur
        malon_total +                                 # malonates
        al_counts["AldehydeCount_AlphaSubstituted"] +
        al_counts["AldehydeCount_BetaSubstituted"] +
        phen +                                        # phenols (total)
        thiophenol_o + thiophenol_m + thiophenol_p +  # positional thiophenols
        nitriles                                      # nitriles are impactful but not Tier 1
    )

    # -----------------------------------------------------------------------
    # RETURN COMPLETE FEATURE DICT
    # -----------------------------------------------------------------------

    return {
        "Valid": 1,

        # === Alcohols ===
        "TotalAlcoholCount": total_alcohols,
        "PrimaryAlcoholCount": primA,
        "SecondaryAlcoholCount": secA,
        "TertiaryAlcoholCount": tertA,
        "PhenolCount": phen,
        "AlphaHydroxyCarbonylCount": alpha_hydroxy,
        "EnolicOHCount": enol_count,
        "AllylicAlcoholCount": allylicA,
        "BenzylicAlcoholCount": benzylicA,
        "PropargylicAlcoholCount": propargylicA,
        "HemiacetalCount": hemiacetalA,
        "HemiketalCount": hemiketalA,
        "Vicinal12DiolCount": vic12,
        "OneThreeDiolCount": one3,
        "IsPolyol": 1 if total_alcohols >= 2 else 0,
        "AlcoholAudit": alcohol_audit,

        # === Aldehydes (detailed) ===
        "AldehydeAudit": aldehyde_audit,
        **al_counts,

        # === Carbonyls / Esters ===
        # === Ethers ===
        "EtherCount": ethers,
        "EtherAliphaticCount": ether_aliphatic,
        "EtherAromaticCount": ether_aromatic,
        "EtherMixedCount": ether_mixed,
        "EtherRingCount": ether_ring,
        "KetoneCount": ketones,
        "EsterCount_Total": esters_total,
        "EsterCount_Open": open_ester_count,
        "LactoneCount": lactone_count,
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

        # === Aromatics / heterocycles ===
        "PyridineCount": pyridines,
        "ThiazoleCount": thiazoles,
        "TerpeneLikeUnitCount": isoprenyls,

        # === Nitro ===
        "NitroGroupCount": nitro_groups,
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
        "NumUnsaturatedBonds": num_unsat_cc,      # strict C–C
        "NumAlkeneBonds": num_alkenes,
        "NumAlkyneBonds": num_alkynes,
        "NumUnsaturatedBonds_All": num_unsat_all, # legacy
        "IsFullySaturated": fully_saturated,

        # === High-impact tiers ===
        # === Totals for S and N ===
        "TotalSulfurGroupCount": (thiols_total + thiophenols + aliph_thiols +
            disulfides + thioesters + thioethers +
            sulfoxides + sulfones),
        "TotalNitrogenGroupCount": (amines_total + nitriles + nitro_groups +
            pyridines + thiazoles),
        "HighImpactTier1Count": high_tier1,
        "HighImpactTier2Count": high_tier2,
        "HighImpactSummary": f"T1:{high_tier1}; T2:{high_tier2}",
    }