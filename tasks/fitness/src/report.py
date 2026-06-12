"""Strength-progression analysis and a dependency-free SVG line chart.

Per session we reduce an exercise to a single "best" number whose meaning depends
on how the lift loads you:

  loaded     -> best estimated 1RM (Epley), so heavier/longer sets rank higher
  assisted   -> the *lowest* assistance weight used (less help = stronger)
  bodyweight -> the most reps in a single set

The chart is plain SVG text — no matplotlib — so it opens anywhere and survives a
later move to Notion or any other tool.
"""
from __future__ import annotations

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from .model import ParseResult, SetRecord, WEIGHT_ASSISTED, WEIGHT_BODYWEIGHT, WEIGHT_LOADED

SANE_REPS = range(1, 41)

CSV_FIELDS = [
    "date", "split", "exercise", "exercise_raw", "weight_type",
    "weight", "unit", "reps", "rpe", "est_1rm", "setup", "note",
]


def to_csv(result: ParseResult, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(CSV_FIELDS)
        for s in sorted(result.sets, key=lambda r: (r.date, r.exercise, r.set_index)):
            w.writerow([
                s.date.isoformat(), s.split or "", s.exercise, s.exercise_raw,
                s.weight_type, s.weight if s.weight is not None else "",
                s.unit, s.reps if s.reps is not None else "",
                s.rpe if s.rpe is not None else "",
                s.est_1rm if s.est_1rm is not None else "",
                s.setup, s.note,
            ])


@dataclass
class ProgressPoint:
    date: date
    value: float        # the metric (e1rm / assist weight / reps)
    detail: str         # human-readable best set, e.g. "95lbs x 6"


@dataclass
class Progression:
    canonical: str
    weight_type: str
    unit: str
    metric_label: str
    higher_is_better: bool
    points: list[ProgressPoint]

    @property
    def change_pct(self) -> Optional[float]:
        if len(self.points) < 2:
            return None
        first, last = self.points[0].value, self.points[-1].value
        if first == 0:
            return None
        delta = (last - first) / first * 100.0
        return round(delta if self.higher_is_better else -delta, 1)


def _dominant_unit(sets: list[SetRecord]) -> str:
    units = Counter(s.unit for s in sets if s.weight is not None)
    return units.most_common(1)[0][0] if units else "lbs"


def progression(result: ParseResult, canonical: str, weight_type: str) -> Progression:
    sets = [s for s in result.by_exercise(canonical) if s.reps in SANE_REPS]
    by_day: dict[date, list[SetRecord]] = defaultdict(list)

    if weight_type == WEIGHT_BODYWEIGHT:
        for s in sets:
            by_day[s.date].append(s)
        points = []
        for d in sorted(by_day):
            best = max(by_day[d], key=lambda s: s.reps)
            points.append(ProgressPoint(d, float(best.reps), f"{best.reps} reps"))
        return Progression(canonical, weight_type, "", "max reps", True, points)

    unit = _dominant_unit(sets)
    sets = [s for s in sets if s.weight is not None and s.unit == unit]
    for s in sets:
        by_day[s.date].append(s)

    points = []
    if weight_type == WEIGHT_ASSISTED:
        for d in sorted(by_day):
            best = min(by_day[d], key=lambda s: (s.weight, -s.reps))
            points.append(ProgressPoint(d, best.weight, f"-{best.weight:g}{unit} x {best.reps}"))
        return Progression(canonical, weight_type, unit, f"assist weight ({unit}, lower=better)", False, points)

    for d in sorted(by_day):
        loaded = [s for s in by_day[d] if s.weight and s.weight > 0]
        if not loaded:  # a loaded lift with 0 external weight isn't a load datapoint
            continue
        best = max(loaded, key=lambda s: s.est_1rm or 0)
        points.append(ProgressPoint(d, best.est_1rm or 0.0, f"{best.weight:g}{unit} x {best.reps}"))
    return Progression(canonical, weight_type, unit, f"est. 1RM ({unit})", True, points)


def progression_table(prog: Progression, display_name: str) -> str:
    lines = [f"# {display_name}  [{prog.canonical}]  — {prog.metric_label}"]
    if not prog.points:
        return "\n".join(lines + ["(no data)"])
    pct = prog.change_pct
    span = f"{prog.points[0].date} → {prog.points[-1].date}, {len(prog.points)} sessions"
    trend = f", trend {pct:+g}%" if pct is not None else ""
    lines.append(span + trend)
    lines.append("")
    for p in prog.points:
        lines.append(f"  {p.date}   {p.value:7g}   {p.detail}")
    return "\n".join(lines)


def _nice_step(span: float) -> float:
    if span <= 0:
        return 1.0
    import math
    raw = span / 4.0
    mag = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag:
            return m * mag
    return 10 * mag


def svg_chart(prog: Progression, display_name: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    W, H = 920, 460
    ml, mr, mt, mb = 70, 30, 56, 60
    pw, ph = W - ml - mr, H - mt - mb
    pts = prog.points

    xs = [p.date.toordinal() for p in pts]
    ys = [p.value for p in pts]
    x0, x1 = min(xs), max(xs)
    if x0 == x1:
        x1 = x0 + 1
    ymin, ymax = min(ys), max(ys)
    pad = (ymax - ymin) * 0.1 or (ymax * 0.1 or 1.0)
    ymin, ymax = ymin - pad, ymax + pad
    invert = not prog.higher_is_better  # assisted: draw so improvement still goes up

    def sx(x: int) -> float:
        return ml + (x - x0) / (x1 - x0) * pw

    def sy(y: float) -> float:
        t = (y - ymin) / (ymax - ymin) if ymax > ymin else 0.5
        if invert:
            t = 1 - t
        return mt + (1 - t) * ph

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" font-family="-apple-system,Helvetica,Arial,sans-serif">',
        f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
        f'<text x="{ml}" y="28" font-size="18" font-weight="600" fill="#111">{_esc(display_name)}</text>',
        f'<text x="{ml}" y="46" font-size="12" fill="#666">{_esc(prog.metric_label)}'
        + (f"  ·  trend {prog.change_pct:+g}%" if prog.change_pct is not None else "")
        + "</text>",
    ]

    # y gridlines + labels
    step = _nice_step(ymax - ymin)
    import math
    g = math.ceil(ymin / step) * step
    while g <= ymax + 1e-9:
        y = sy(g)
        parts.append(f'<line x1="{ml}" y1="{y:.1f}" x2="{ml+pw}" y2="{y:.1f}" stroke="#eee"/>')
        parts.append(f'<text x="{ml-8}" y="{y+4:.1f}" font-size="11" fill="#888" text-anchor="end">{g:g}</text>')
        g += step

    # x axis date labels (first, last, and a couple inside)
    n = len(pts)
    idxs = sorted({0, n - 1, n // 3, 2 * n // 3})
    for i in idxs:
        x = sx(xs[i])
        parts.append(f'<line x1="{x:.1f}" y1="{mt+ph}" x2="{x:.1f}" y2="{mt+ph+5}" stroke="#aaa"/>')
        parts.append(f'<text x="{x:.1f}" y="{mt+ph+20}" font-size="11" fill="#888" text-anchor="middle">{pts[i].date.strftime("%y-%m-%d")}</text>')

    parts.append(f'<rect x="{ml}" y="{mt}" width="{pw}" height="{ph}" fill="none" stroke="#ccc"/>')
    poly = " ".join(f"{sx(xs[i]):.1f},{sy(ys[i]):.1f}" for i in range(n))
    parts.append(f'<polyline points="{poly}" fill="none" stroke="#2563eb" stroke-width="2"/>')
    for i in range(n):
        parts.append(f'<circle cx="{sx(xs[i]):.1f}" cy="{sy(ys[i]):.1f}" r="2.6" fill="#2563eb"/>')
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
