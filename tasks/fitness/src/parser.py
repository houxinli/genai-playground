"""Parse the freeform Apple-Notes workout log into structured `SetRecord`s.

The log is written newest-first, dates are `M.D` with no year, and two notations
coexist:

  modern (≈2025-2026):  <name> [setup] <weight>lbs <reps> rpe<n> <reps> rpe<n> ...
  compact (≈2024):      <name> <weight> <sets> <reps>     (or <sets> <reps> for bodyweight)

The parser is deliberately conservative: lines it cannot read cleanly become
`ParseIssue`s rather than guessed-at sets, so the CSV stays trustworthy.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Callable, Optional

from .model import (
    ParseIssue,
    ParseResult,
    SetRecord,
    WEIGHT_ASSISTED,
    WEIGHT_BODYWEIGHT,
    WEIGHT_LOADED,
)

# A callable raw_name -> (canonical_slug, weight_type). Defaults to a no-op below.
Normalizer = Callable[[str], tuple[str, str]]

PLAUSIBLE_SET_COUNTS = {1, 2, 3, 4, 5, 6}

_HEADER_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})\b\s*(.*)$")
_WEIGHT_RE = re.compile(r"^(\d+(?:\.\d+)?)(lbs|lb|kg)$", re.IGNORECASE)
_BAR_RE = re.compile(r"^bar(?:\+(\d+(?:\.\d+)?))?$", re.IGNORECASE)
_RPE_RE = re.compile(r"^rpe(\d+(?:\.\d+)?)")
_NUM_RE = re.compile(r"^(\d+(?:\.\d+)?)$")
_SETUP_RE = re.compile(r"^\d+deg$")


def _default_normalizer(raw: str) -> tuple[str, str]:
    slug = re.sub(r"\s+", "_", raw.strip().lower())
    return slug, WEIGHT_LOADED


def _split_label(rest: str) -> Optional[str]:
    low = rest.lower()
    if "push" in low:
        return "push"
    if "pull" in low:
        return "pull"
    if "leg" in low:
        return "leg"
    return None


def _parse_header(line: str) -> Optional[tuple[int, int, Optional[str]]]:
    stripped = line.strip().lstrip("#").strip().strip("*").strip()
    m = _HEADER_RE.match(stripped)
    if not m:
        return None
    month, day = int(m.group(1)), int(m.group(2))
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    return month, day, _split_label(m.group(3))


def _clean_line(raw: str) -> tuple[str, list[str]]:
    """Normalize punctuation, lift out parenthetical notes, glue/split stuck tokens."""
    s = raw.replace("（", "(").replace("）", ")").replace("：", ":")
    notes: list[str] = []
    for m in re.finditer(r"\(([^)]*)\)", s):
        text = m.group(1).strip()
        if text:
            notes.append(text)
    s = re.sub(r"\([^)]*\)", " ", s)

    # per-hand dumbbell markers "20*2" / "20 * 2" -> keep the per-hand weight only
    s = re.sub(r"\*\s*2\b", " ", s)
    s = s.replace("*", " ")
    s = re.sub(r"/?\bea\b", " ", s)  # word "ea" only — must not touch "deadlift"
    # detach a name glued to a 上X下Y machine marker: "窄距卧推上9下6" -> "窄距卧推 上9下6"
    s = re.sub(r"([一-鿿])(上[A-Za-z0-9])", r"\1 \2", s)
    # peel a stuck "<reps>rpe" apart first: "20rpe8" -> "20 rpe8"
    s = re.sub(r"(\d)\s*rpe", r"\1 rpe", s, flags=re.IGNORECASE)
    # detach a name glued to a trailing number: "rdl15" / "推举60deg" -> "rdl 15" / "推举 60deg"
    # (also splits "rpe8" -> "rpe 8"; the rpe glue at the end puts it back together)
    # never split inside a 上../下.. marker (上9, 下8, ...)
    s = re.sub(r"((?:[A-Za-z]|(?![上下])[一-鿿]))(\d)", r"\1 \2", s)
    # angle / degree -> a single setup token: "45 degree" / "45 deg" -> "45deg"
    s = re.sub(r"(\d+)\s*(?:degree|deg|度)\b", r"\1deg", s, flags=re.IGNORECASE)
    # weight unit glue/split: "15 lbs" -> "15lbs", "95lbs3" -> "95lbs 3"
    s = re.sub(r"(\d)\s*(lbs|lb|kg)\b", r"\1\2", s, flags=re.IGNORECASE)
    s = re.sub(r"(lbs|lb|kg)(\d)", r"\1 \2", s, flags=re.IGNORECASE)
    # rejoin rpe with its number: "rpe 8" -> "rpe8"
    s = re.sub(r"rpe\s*(\d)", r"rpe\1", s, flags=re.IGNORECASE)
    return s, notes


def _is_name_token(tok: str) -> bool:
    if tok.lower() in {"lbs", "lb", "kg"}:
        return False
    if tok.startswith("上") or tok.startswith("下"):
        return False
    if any(ch.isdigit() for ch in tok):
        return False
    return bool(re.match(r"^[A-Za-z一-鿿/+\-]+$", tok))


def _split_name(tokens: list[str]) -> tuple[str, list[str], list[str]]:
    setup: list[str] = []
    i = 0
    while i < len(tokens) and _SETUP_RE.match(tokens[i]):  # leading angle: "45deg bench press"
        setup.append(tokens[i])
        i += 1
    name_tokens: list[str] = []
    while i < len(tokens) and _is_name_token(tokens[i]):
        name_tokens.append(tokens[i])
        i += 1
    if not name_tokens and i < len(tokens):  # e.g. "21s" — first token carries the name
        name_tokens.append(tokens[i])
        i += 1
    return " ".join(name_tokens), tokens[i:], setup


def _peel_setup(tokens: list[str]) -> tuple[list[str], list[str]]:
    """Pull leading setup tokens (angles, machine markers) off the front."""
    setup: list[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if _SETUP_RE.match(tok) or tok.startswith("上") or tok.startswith("下"):
            setup.append(tok)
            i += 1
        else:
            break
    return setup, tokens[i:]


def _classify(tok: str):
    m = _WEIGHT_RE.match(tok)
    if m:
        return ("weight", float(m.group(1)), m.group(2).lower())
    m = _BAR_RE.match(tok)
    if m:
        return ("weight", float(m.group(1)) if m.group(1) else 0.0, "bar")
    m = _RPE_RE.match(tok)
    if m:
        return ("rpe", float(m.group(1)), None)
    m = _NUM_RE.match(tok)
    if m:
        val = float(m.group(1))
        return ("num", int(val) if val.is_integer() else val, None)
    return ("word", tok, None)


def _emit(records, ctx, reps, rpe):
    records.append(
        SetRecord(
            date=ctx["date"],
            split=ctx["split"],
            exercise_raw=ctx["raw"],
            exercise=ctx["canon"],
            weight_type=ctx["wtype"],
            weight=ctx["weight"],
            unit=ctx["unit"],
            reps=reps,
            rpe=rpe,
            setup=ctx["setup"],
            note=ctx["note"],
            set_index=len(records) + 1,
            raw_line=ctx["line"],
        )
    )


def _parse_modern(stream: list[str], ctx: dict) -> list[SetRecord]:
    records: list[SetRecord] = []
    pending: Optional[int] = None
    extra_notes: list[str] = []
    for tok in stream:
        kind, a, b = _classify(tok)
        if kind == "weight":
            if pending is not None:
                _emit(records, ctx, pending, None)
                pending = None
            ctx["weight"], ctx["unit"] = a, b
        elif kind == "rpe":
            if pending is not None:
                _emit(records, ctx, pending, a)
                pending = None
            elif records:  # rpe with no fresh reps: another set at the previous reps
                _emit(records, ctx, records[-1].reps, a)
        elif kind == "num":
            if pending is not None:
                _emit(records, ctx, pending, None)
            pending = a
        else:
            extra_notes.append(a)
    if pending is not None:
        _emit(records, ctx, pending, None)
    if extra_notes:
        joined = " ".join(extra_notes)
        for r in records:
            r.note = (r.note + " " + joined).strip() if r.note else joined
    return records


def _parse_compact(nums: list[float], ctx: dict) -> Optional[list[SetRecord]]:
    """Old `weight sets reps` / `sets reps` / repeated-reps notation."""
    ints = [int(n) for n in nums]
    records: list[SetRecord] = []
    if len(ints) == 3:
        weight, sets, reps = ints
        all_equal = ints[0] == ints[1] == ints[2]
        if sets in PLAUSIBLE_SET_COUNTS and not all_equal:
            ctx["weight"] = float(weight) if ctx["wtype"] != WEIGHT_BODYWEIGHT else None
            for _ in range(sets):
                _emit(records, ctx, reps, None)
            return records
        for r in ints:  # treat as three reps-only sets
            _emit(records, ctx, r, None)
        return records
    if len(ints) == 2:
        first, second = ints
        if first in PLAUSIBLE_SET_COUNTS:
            for _ in range(first):
                _emit(records, ctx, second, None)
            return records
        for r in ints:
            _emit(records, ctx, r, None)
        return records
    return None


def parse_log(text: str, today: Optional[date] = None, normalizer: Optional[Normalizer] = None) -> ParseResult:
    today = today or date.today()
    normalize = normalizer or _default_normalizer
    result = ParseResult()

    year = today.year
    prev_month: Optional[int] = None
    cur_date: Optional[date] = None
    cur_split: Optional[str] = None

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue

        header = _parse_header(line)
        if header:
            month, day, split = header
            if prev_month is not None and month > prev_month + 2:
                year -= 1  # crossed a Dec->Jan boundary going back in time
            prev_month = month
            try:
                cur_date = date(year, month, day)
            except ValueError:
                cur_date = None
            cur_split = split
            result.sessions += 1
            continue

        if cur_date is None:
            continue  # text before the first dated header (title etc.)

        cleaned, notes = _clean_line(line)
        tokens = cleaned.split()
        if not tokens:
            continue
        raw_name, rest, lead_setup = _split_name(tokens)
        more_setup, rest = _peel_setup(rest)
        setup = " ".join(lead_setup + more_setup)
        canon, wtype = normalize(raw_name)

        ctx = {
            "date": cur_date, "split": cur_split, "raw": raw_name, "canon": canon,
            "wtype": wtype, "weight": None, "unit": "lbs",
            "setup": setup, "note": "; ".join(notes), "line": line,
        }

        has_weight = any(_classify(t)[0] == "weight" for t in rest)
        has_rpe = any(_classify(t)[0] == "rpe" for t in rest)
        bare = [_classify(t)[1] for t in rest if _classify(t)[0] == "num"]

        if has_weight or has_rpe:
            records = _parse_modern(rest, ctx)
        elif 2 <= len(bare) <= 3 and len(bare) == sum(
            1 for t in rest if _classify(t)[0] == "num"
        ):
            records = _parse_compact(bare, ctx) or []
        else:
            records = []

        if records:
            result.sets.extend(records)
        else:
            result.issues.append(
                ParseIssue(date=cur_date, raw_line=line, reason="no parseable sets")
            )

    return result
