"""Utility helpers shared by rating fetchers."""

from __future__ import annotations

import math
import re
import unicodedata
from typing import Iterable, Optional


_NON_WORD_RE = re.compile(r"[^a-z0-9]+")


def normalize_title(title: str) -> str:
    text = unicodedata.normalize("NFKD", title).casefold()
    text = _NON_WORD_RE.sub(" ", text).strip()
    return re.sub(r"\s+", " ", text)


def title_similarity(a: str, b: str) -> float:
    na = normalize_title(a)
    nb = normalize_title(b)
    if not na or not nb:
        return 0.0
    set_a = set(na.split())
    set_b = set(nb.split())
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    if union == 0:
        return 0.0
    return intersection / union


def pick_best_candidate(candidates: Iterable[dict], *, title: str, year: Optional[int]) -> Optional[dict]:
    best: Optional[dict] = None
    best_score = 0.0
    for item in candidates:
        cand_title = item.get("title") or item.get("name") or item.get("l")
        if not cand_title:
            continue
        sim = title_similarity(title, cand_title)
        if sim < 0.3:
            continue
        score = sim
        if year and (candidate_year := _extract_year(item)):
            diff = abs(candidate_year - year)
            score -= math.log2(1 + diff)
        if score > best_score:
            best_score = score
            best = item
    return best


def _extract_year(data: dict) -> Optional[int]:
    for key in ("year", "y", "releaseYear"):
        value = data.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None

