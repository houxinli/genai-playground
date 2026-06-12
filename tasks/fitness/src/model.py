"""Data model for parsed workout sets.

One `SetRecord` is the atomic unit: a single working set of one exercise on one
day. Sessions and entries are kept light — the CSV/report layer works off the
flat list of `SetRecord`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


WEIGHT_LOADED = "loaded"          # more external weight = stronger (bench, rdl, ...)
WEIGHT_ASSISTED = "assisted"      # less assistance = stronger (assisted chin up, dip assist)
WEIGHT_BODYWEIGHT = "bodyweight"  # no external load; progress = reps (push up, plank)


@dataclass
class SetRecord:
    date: date
    split: Optional[str]            # push / pull / leg / None
    exercise_raw: str               # name exactly as written, cleaned of set data
    exercise: str                   # canonical slug from the glossary
    weight_type: str = WEIGHT_LOADED
    weight: Optional[float] = None  # external load; for assisted = assist weight
    unit: str = "lbs"               # lbs / kg
    reps: Optional[int] = None
    rpe: Optional[float] = None
    setup: str = ""                 # machine setup notes (60deg, 上F下8, ...)
    note: str = ""                  # free annotations (grip issue, 拿放, ...)
    set_index: int = 0              # 1-based order within the exercise entry
    raw_line: str = ""              # original line, for debugging / round-trip

    @property
    def est_1rm(self) -> Optional[float]:
        """Epley estimated 1RM. Only meaningful for loaded sets with weight+reps."""
        if self.weight_type != WEIGHT_LOADED:
            return None
        if self.weight is None or self.reps is None or self.reps <= 0:
            return None
        return round(self.weight * (1 + self.reps / 30.0), 1)

    @property
    def volume(self) -> Optional[float]:
        if self.weight is None or self.reps is None:
            return None
        return round(self.weight * self.reps, 1)


@dataclass
class ParseIssue:
    """A line the parser could not turn into clean sets, kept for honest reporting."""
    date: Optional[date]
    raw_line: str
    reason: str


@dataclass
class ParseResult:
    sets: list[SetRecord] = field(default_factory=list)
    issues: list[ParseIssue] = field(default_factory=list)
    sessions: int = 0

    def by_exercise(self, canonical: str) -> list[SetRecord]:
        return [s for s in self.sets if s.exercise == canonical]
