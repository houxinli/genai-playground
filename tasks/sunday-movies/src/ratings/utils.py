"""Utility helpers shared by rating fetchers."""

from __future__ import annotations

import math
import re
import unicodedata
from typing import Iterable, Optional


_NON_WORD_RE = re.compile(r"[^a-z0-9]+")

# Suffixes that appear on theater listings but hurt rating-source search.
_SEARCH_NOISE_RE = re.compile(
    r"""
    \(\d{4}\)                                   # trailing (2026)
    | \b\d+\s*(?:st|nd|rd|th)\s+anniversary\b   # 25th Anniversary
    | \b(?:re-?release|encore|fathom\ events?)\b
    | \b(?:real ?d\ ?3d|imax(?:\ 3d)?|3d|dolby\ (?:cinema|atmos)|prime|xd)\b
    | \b(?:live\ viewing|live\ in\ concert|the\ concert\ film)\b
    """,
    re.IGNORECASE | re.VERBOSE,
)


def normalize_title(title: str) -> str:
    text = unicodedata.normalize("NFKD", title).casefold()
    text = _NON_WORD_RE.sub(" ", text).strip()
    return re.sub(r"\s+", " ", text)


def extract_title_year(title: str) -> Optional[int]:
    """Pull a 4-digit release year out of a theater title, if present."""
    match = re.search(r"\((\d{4})\)", title)
    if not match:
        # also accept a bare trailing year token, e.g. "Movie 2026"
        match = re.search(r"\b(19|20)\d{2}\b\s*$", title)
        if not match:
            return None
        return int(match.group(0))
    year = int(match.group(1))
    return year if 1900 <= year <= 2100 else None


def clean_search_title(title: str) -> str:
    """Strip release-format / anniversary noise so rating searches match better.

    Keeps the original casing/words; only removes known noise tokens and a
    trailing 4-digit year. Falls back to the original title if cleaning would
    empty it out (e.g. a concert listing that is mostly noise tokens)."""
    cleaned = _SEARCH_NOISE_RE.sub(" ", title)
    cleaned = re.sub(r"[:\-–—]+\s*$", "", cleaned.strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or title.strip()


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

