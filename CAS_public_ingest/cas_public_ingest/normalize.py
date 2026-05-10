from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Tuple

CAS_RE = re.compile(r"^\s*([0-9]{2,7})\s*-\s*([0-9]{2})\s*-\s*([0-9])\s*$")


def normalize_cas(cas_raw: str) -> Optional[str]:
    """
    Normalize a CAS RN to the canonical hyphenated form: X...X-XX-X
    Returns None if it does not look like a CAS RN.
    """
    if cas_raw is None:
        return None
    m = CAS_RE.match(str(cas_raw))
    if not m:
        return None
    a, b, c = m.group(1), m.group(2), m.group(3)
    return f"{int(a)}-{b}-{c}"


def cas_checksum_ok(cas_norm: str) -> bool:
    """
    Validate CAS RN checksum.
    Algorithm: remove hyphens; last digit is checksum.
    Multiply digits from right to left (excluding checksum) by 1..n; sum; mod 10 == checksum.
    """
    m = CAS_RE.match(cas_norm)
    if not m:
        return False
    digits = (m.group(1) + m.group(2) + m.group(3))
    body, checksum = digits[:-1], int(digits[-1])
    total = 0
    factor = 1
    for ch in reversed(body):
        total += int(ch) * factor
        factor += 1
    return (total % 10) == checksum


def clean_name(name: str) -> str:
    if name is None:
        return ""
    return " ".join(str(name).strip().split())


@dataclass(frozen=True)
class ParsedIFRARow:
    cas_raw: str
    cas: Optional[str]
    cas_checksum_ok: Optional[bool]
    principal_name: str
    ncs_category: str
    source_url: str
    retrieved_at: str
