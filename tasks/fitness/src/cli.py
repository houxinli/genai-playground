"""Command-line entry for the fitness log.

    python tasks/fitness/src/cli.py parse
    python tasks/fitness/src/cli.py exercises
    python tasks/fitness/src/cli.py progress machine_shoulder_press
    python tasks/fitness/src/cli.py chart 坐姿杠铃推举
    python tasks/fitness/src/cli.py chart-all --min-sessions 6
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import date
from pathlib import Path

if __package__ in (None, ""):  # allow running as a plain script
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from fitness.src import report
    from fitness.src.normalize import Normalizer
    from fitness.src.parser import parse_log
else:
    from . import report
    from .normalize import Normalizer
    from .parser import parse_log

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOG = ROOT / "data" / "workout_log.md"
DERIVED = ROOT / "data" / "derived"


def _load(args):
    text = Path(args.log).read_text(encoding="utf-8")
    nz = Normalizer()
    today = date.fromisoformat(args.today) if args.today else date.today()
    return parse_log(text, today=today, normalizer=nz), nz


def _resolve(nz: Normalizer, name: str) -> str:
    if name in nz.exercises:
        return name
    canon, _ = nz(name)
    return canon


def cmd_parse(args):
    result, _ = _load(args)
    out = Path(args.out) if args.out else DERIVED / "sets.csv"
    report.to_csv(result, out)
    dates = [s.date for s in result.sets]
    date_range = f"  ({min(dates)} → {max(dates)})" if dates else ""
    print(f"sessions: {result.sessions}")
    print(f"sets:     {len(result.sets)}{date_range}")
    print(f"issues:   {len(result.issues)} lines could not be parsed into sets")
    print(f"csv:      {out}")
    if args.show_issues:
        print("\n-- unparsed lines (sample) --")
        for iss in result.issues[: args.show_issues]:
            print(f"  {iss.date}  {iss.raw_line}")


def cmd_exercises(args):
    result, nz = _load(args)
    counts = Counter(s.exercise for s in result.sets)
    sessions = {c: len({s.date for s in result.sets if s.exercise == c}) for c in counts}
    print(f"{'sets':>5} {'days':>5}  {'type':<10} {'muscle':<10} exercise")
    for canon, n in counts.most_common():
        meta = nz.exercises.get(canon, {})
        flag = "" if canon in nz.exercises else "  (unmapped)"
        print(f"{n:>5} {sessions[canon]:>5}  {meta.get('weight_type','?'):<10} "
              f"{meta.get('muscle','?'):<10} {nz.display_name(canon)}{flag}")


def _weight_type(nz: Normalizer, canon: str) -> str:
    return nz.exercises.get(canon, {}).get("weight_type", "loaded")


def cmd_progress(args):
    result, nz = _load(args)
    canon = _resolve(nz, args.exercise)
    prog = report.progression(result, canon, _weight_type(nz, canon))
    print(report.progression_table(prog, nz.display_name(canon)))


def cmd_chart(args):
    result, nz = _load(args)
    canon = _resolve(nz, args.exercise)
    prog = report.progression(result, canon, _weight_type(nz, canon))
    if not prog.points:
        print(f"no chartable data for {canon}")
        return
    out = Path(args.out) if args.out else DERIVED / "charts" / f"{canon}.svg"
    report.svg_chart(prog, nz.display_name(canon), out)
    print(f"wrote {out}  ({len(prog.points)} sessions)")


def cmd_chart_all(args):
    result, nz = _load(args)
    out_dir = Path(args.out) if args.out else DERIVED / "charts"
    counts = Counter(s.exercise for s in result.sets)
    made = 0
    for canon in counts:
        if canon not in nz.exercises:
            continue
        prog = report.progression(result, canon, _weight_type(nz, canon))
        if len(prog.points) < args.min_sessions:
            continue
        report.svg_chart(prog, nz.display_name(canon), out_dir / f"{canon}.svg")
        made += 1
    print(f"wrote {made} charts to {out_dir} (>= {args.min_sessions} sessions)")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Parse and chart the freeform workout log.")
    p.add_argument("--log", default=str(DEFAULT_LOG), help="path to the freeform log")
    p.add_argument("--today", default=None, help="anchor date YYYY-MM-DD for year inference")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("parse", help="parse log -> sets.csv")
    sp.add_argument("--out", default=None)
    sp.add_argument("--show-issues", type=int, default=0, metavar="N")
    sp.set_defaults(func=cmd_parse)

    sp = sub.add_parser("exercises", help="list canonical exercises with counts")
    sp.set_defaults(func=cmd_exercises)

    sp = sub.add_parser("progress", help="text progression for one exercise")
    sp.add_argument("exercise", help="canonical slug or any alias")
    sp.set_defaults(func=cmd_progress)

    sp = sub.add_parser("chart", help="SVG progression chart for one exercise")
    sp.add_argument("exercise")
    sp.add_argument("--out", default=None)
    sp.set_defaults(func=cmd_chart)

    sp = sub.add_parser("chart-all", help="SVG charts for every mapped exercise")
    sp.add_argument("--out", default=None)
    sp.add_argument("--min-sessions", type=int, default=6)
    sp.set_defaults(func=cmd_chart_all)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
