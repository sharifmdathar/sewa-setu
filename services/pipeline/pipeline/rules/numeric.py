"""Numeric helpers shared by the C4/C5 checks."""

from __future__ import annotations


def is_power_of_ten_ratio(a: int, b: int) -> bool:
    """True when one value is the other with whole decimal zeros appended (10x, 100x).

    This is the classic "add a zero" amount forgery: it is a fraud signal (C5), not a
    declaration mismatch (C4), so both checks need to agree on the predicate.
    """
    if a <= 0 or b <= 0 or a == b:
        return False
    high, low = (a, b) if a >= b else (b, a)
    if high % low:
        return False
    ratio = high // low
    while ratio % 10 == 0:
        ratio //= 10
    return ratio == 1


def short_hash(sha256: str, length: int = 12) -> str:
    return sha256[:length] if len(sha256) > length else sha256
