import datetime as dt
import re
import pandas as pd

from .constants import (
    SPLIT_REGEX,
    CAS_REGEX,
    YMD_TIME_REGEX,
    SLASH_TIME_REGEX,
    ADJ_DIGITS,
)

def compact_ws(s: str) -> str:
    """Collapse whitespace to single spaces and strip."""
    return re.sub(r"\s+", " ", str(s)).strip()

def is_all_zero_cas_like(token: str) -> bool:
    """True if digits extracted from token exist and are all zeros."""
    digits = re.sub(r"[^0-9]", "", str(token))
    return bool(digits) and set(digits) == {"0"}

def split_cas_cell(val) -> list:
    """Split CAS cell into tokens, preserving order."""
    if val is None:
        return []
    try:
        if pd.isna(val):
            return []
    except Exception:
        pass

    if isinstance(val, (pd.Timestamp, dt.datetime, dt.date)):
        if isinstance(val, pd.Timestamp):
            val = val.to_pydatetime()
        if isinstance(val, dt.datetime):
            val = val.date()
        return [val.strftime("%Y-%m-%d")]

    s = compact_ws(str(val).replace("\u00a0", " "))
    if not s:
        return []
    parts = SPLIT_REGEX.split(s)
    return [p.strip() for p in parts if p and p.strip()]

def is_valid_cas(cas: str) -> bool:
    """Strict CAS regex + checksum; reject all-zero placeholder."""
    cas = str(cas).strip()
    if not CAS_REGEX.fullmatch(cas):
        return False
    digits = cas.replace("-", "")
    if set(digits) == {"0"}:
        return False

    check = int(digits[-1])
    body = digits[:-1]
    total = 0
    for i, ch in enumerate(reversed(body), start=1):
        total += int(ch) * i
    return (total % 10) == check

def is_date_like(s: str) -> bool:
    """True if string is YYYY-MM-DD[ time] or slash-date[ time]."""
    s = compact_ws(s)
    return bool(YMD_TIME_REGEX.fullmatch(s) or SLASH_TIME_REGEX.fullmatch(s))

def try_recover_from_date_string(s: str) -> str | None:
    """Recover from Excel date conversion ONLY if checksum validates."""
    s = compact_ws(s)

    m = YMD_TIME_REGEX.fullmatch(s)
    if m:
        y, mm, dd = m.group(1), m.group(2), m.group(3)
        try:
            day_i = int(dd)
            if dd.startswith("0") and 1 <= day_i <= 9:
                cand = f"{y}-{mm}-{day_i}"
                if is_valid_cas(cand):
                    return cand
        except Exception:
            pass
        return None

    ms = SLASH_TIME_REGEX.fullmatch(s)
    if ms:
        a, b, y = ms.group(1), ms.group(2), ms.group(3)
        for month, day in [(a, b), (b, a)]:
            try:
                mi = int(month)
                di = int(day)
                if 1 <= mi <= 12 and 1 <= di <= 31:
                    mm = f"{mi:02d}"
                    dd = f"{di:02d}"
                    if dd.startswith("0") and 1 <= di <= 9:
                        cand = f"{y}-{mm}-{di}"
                        if is_valid_cas(cand):
                            return cand
            except Exception:
                continue
    return None

def rehyphenate_from_digits(digits: str) -> str | None:
    """Strip digits and format as <all but last3>-<next2>-<last1> if valid."""
    if not re.fullmatch(r"\d{5,10}", digits):
        return None
    first = digits[:-3]
    mid = digits[-3:-1]
    last = digits[-1]
    if not (2 <= len(first) <= 7):
        return None
    cand = f"{first}-{mid}-{last}"
    return cand if is_valid_cas(cand) else None

def try_fix_missing_checkdigit(token: str) -> str | None:
    """If token matches d{2,7}-d{2}, try appending -0..-9."""
    token = str(token).strip()
    if not re.fullmatch(r"\d{2,7}-\d{2}", token):
        return None
    for d in "0123456789":
        cand = f"{token}-{d}"
        if is_valid_cas(cand):
            return cand
    return None

def unique_preserve_order(seq: list[str]) -> list:
    """Return unique elements in original order."""
    out = []
    seen = set()
    for x in seq:
        if x not in seen:
            out.append(x)
            seen.add(x)
    return out

def adjacent_swap_variants(token: str) -> list:
    """Swap adjacent characters ONCE (including '-' dash). Returns raw variants."""
    t = str(token).strip().replace(" ", "")
    if not t:
        return []
    chars = list(t)
    res = []
    for i in range(len(chars) - 1):
        swapped = chars.copy()
        swapped[i], swapped[i + 1] = swapped[i + 1], swapped[i]
        res.append("".join(swapped))
    return unique_preserve_order(res)

def adjacent_key_substitution_variants(token: str) -> list:
    """Substitute ONE digit to an adjacent digit (keyboard row OR numpad adjacency)."""
    t = str(token).strip().replace(" ", "")
    if not t:
        return []
    chars = list(t)
    res = []
    for i, ch in enumerate(chars):
        if ch.isdigit():
            for d in ADJ_DIGITS.get(ch, set()):
                if d == ch:
                    continue
                cand = chars.copy()
                cand[i] = d
                res.append("".join(cand))
    return unique_preserve_order(res)

def build_evidence_indexes(df: pd.DataFrame) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Evidence maps from VALID CAS found anywhere in dataset."""
    by_code: dict[str, set[str]] = {}
    by_desig: dict[str, set[str]] = {}

    for _, r in df.iterrows():
        code = str(r.get("Code Unique", "")).strip()
        desig = compact_ws(r.get("Designation", "")).upper()

        for tok in split_cas_cell(r.get("CAS")):
            tok2 = compact_ws(tok)
            if is_valid_cas(tok2):
                by_code.setdefault(code, set()).add(tok2)
                by_desig.setdefault(desig, set()).add(tok2)
            else:
                rec = try_recover_from_date_string(tok2)
                if rec:
                    by_code.setdefault(code, set()).add(rec)
                    by_desig.setdefault(desig, set()).add(rec)

    return by_code, by_desig

def choose_best_candidate(
    candidates: list[str],
    code: str,
    desig: str,
    by_code: dict[str, set[str]],
    by_desig: dict[str, set[str]],
    allow_unique_no_evidence: bool = False,
) -> tuple[str | None, list[str]]:
    """Score: +2 if seen with same Code Unique, +1 if seen with same Designation."""
    candidates = unique_preserve_order(candidates)
    if not candidates:
        return None, []

    if allow_unique_no_evidence and len(candidates) == 1:
        return candidates[0], candidates

    code = str(code).strip()
    desig_key = compact_ws(desig).upper()

    scored = []
    for c in candidates:
        score = 0
        if c in by_code.get(code, set()):
            score += 2
        if c in by_desig.get(desig_key, set()):
            score += 1
        scored.append((score, c))

    scored_sorted = sorted(scored, key=lambda x: x[0], reverse=True)
    best_score = scored_sorted[0][0]
    best = [c for s, c in scored_sorted if s == best_score]
    ranked = [c for _, c in scored_sorted]

    if best_score > 0 and len(best) == 1:
        return best[0], ranked

    return None, ranked

def date_like_edit_to_cas_candidates(original: str) -> list:
    """For a date-like token, generate 1-edit variants, then recover valid CAS."""
    base = compact_ws(original)
    variants = []
    variants.extend(adjacent_swap_variants(base))
    variants.extend(adjacent_key_substitution_variants(base))
    variants = unique_preserve_order(variants)

    hits = []
    for v in variants:
        cas = try_recover_from_date_string(v)
        if cas and is_valid_cas(cas):
            hits.append((cas, v))

    out, seen = [], set()
    for cas, v in hits:
        if cas not in seen:
            out.append((cas, v))
            seen.add(cas)
    return out

def normalize_and_repair_token(
    original_token: str,
    code: str,
    desig: str,
    by_code: dict[str, set[str]],
    by_desig: dict[str, set[str]],
) -> tuple[str, str]:
    """Returns (output_token, status_text)."""
    orig = compact_ws(original_token)
    if not orig:
        return "", "invalid (original: )"

    if is_valid_cas(orig):
        return orig, "valid"

    rec = try_recover_from_date_string(orig)
    if rec:
        return rec, f"valid (fixed from: {orig})"

    if is_date_like(orig):
        hits = date_like_edit_to_cas_candidates(orig)
        cas_candidates = [cas for cas, _via in hits]

        chosen, ranked = choose_best_candidate(
            cas_candidates, code, desig, by_code, by_desig, allow_unique_no_evidence=False
        )
        if chosen:
            via = next((v for cas, v in hits if cas == chosen), "")
            return chosen, f"valid (fixed via date-edit from: {orig}; via: {via})"

        if hits:
            top = hits[:5]
            sugg = " | ".join([f"{cas} (via {via})" for cas, via in top])
            return orig, f"invalid (original: {orig}; suggestions: {sugg})"

    swap_vars = adjacent_swap_variants(orig)
    swap_valid = [v for v in swap_vars if is_valid_cas(v)]
    swap_valid = unique_preserve_order(swap_valid)

    chosen, ranked = choose_best_candidate(
        swap_valid, code, desig, by_code, by_desig, allow_unique_no_evidence=True
    )
    if chosen:
        return chosen, f"valid (fixed swap from: {orig})"
    if swap_valid:
        sugg = " | ".join(ranked[:5])
        return orig, f"invalid (original: {orig}; suggestions: {sugg})"

    if CAS_REGEX.fullmatch(orig):
        sub_vars = adjacent_key_substitution_variants(orig)
        sub_valid = [v for v in sub_vars if is_valid_cas(v)]
        sub_valid = unique_preserve_order(sub_valid)

        chosen, ranked = choose_best_candidate(
            sub_valid, code, desig, by_code, by_desig, allow_unique_no_evidence=False
        )
        if chosen:
            return chosen, f"valid (fixed adjacent-key from: {orig})"
        if sub_valid:
            sugg = " | ".join(ranked[:5])
            return orig, f"invalid (original: {orig}; suggestions: {sugg})"

    digits = re.sub(r"[^0-9]", "", orig)
    reh = rehyphenate_from_digits(digits)
    if reh:
        return reh, f"valid (fixed rehyphenated from: {orig})"

    cd = try_fix_missing_checkdigit(orig)
    if cd:
        return cd, f"valid (fixed checkdigit from: {orig})"

    return orig, f"invalid (original: {orig})"

def build_fixed_cas_cell(
    original_cell,
    code: str,
    desig: str,
    by_code: dict[str, set[str]],
    by_desig: dict[str, set[str]],
) -> str:
    """Mimic the original CAS cell but cleaned."""
    toks = split_cas_cell(original_cell)
    out_tokens = []

    for tok in toks:
        tok_clean = compact_ws(tok)
        if not tok_clean:
            continue

        if is_all_zero_cas_like(tok_clean):
            continue

        cas_out, _status = normalize_and_repair_token(tok_clean, code, desig, by_code, by_desig)

        if is_valid_cas(cas_out) and not is_all_zero_cas_like(cas_out):
            out_tokens.append(cas_out)
        else:
            out_tokens.append(f"{tok_clean} (invalid)")

    return " / ".join(out_tokens)