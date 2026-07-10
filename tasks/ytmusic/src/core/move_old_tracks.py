from __future__ import annotations

import csv
import json
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

from tasks.ytmusic.src.core.normalize import is_foreign
from tasks.ytmusic.src.ytmusic.sync_pipeline import apply_csv_to_playlist, sort_rows


def parse_year(val: str) -> Optional[int]:
    if not val:
        return None
    try:
        return int(str(val).split("-")[0])
    except Exception:
        return None


def compute_cutoff_date(older_than: int, now_year: Optional[int] = None, today: Optional[date] = None) -> str:
    """
    满 older_than 年的分界日(ISO)。release_date <= 该日即应移出。
    指定 now_year 时保持旧的按年语义(发行年 <= now_year - older_than);
    否则按今天精确到日往前推 older_than 年。
    """
    if now_year is not None:
        return f"{now_year - older_than}-12-31"
    today = today or datetime.now().date()
    try:
        return today.replace(year=today.year - older_than).isoformat()
    except ValueError:  # 2月29日
        return today.replace(year=today.year - older_than, day=28).isoformat()


def load_csv(path: Path) -> List[Dict[str, str]]:
    return list(csv.DictReader(path.open()))


def write_csv(rows: List[Dict[str, str]], path: Path) -> None:
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in fieldnames})


def _merge_into(target_rows: List[Dict[str, str]], moving: List[Dict[str, str]]) -> List[Dict[str, str]]:
    def key_fn(r: Dict[str, str]) -> str:
        return (r.get("title", "") + "|" + r.get("artists", "")).strip()

    keys = {key_fn(r) for r in target_rows}
    for r in moving:
        k = key_fn(r)
        if k not in keys:
            target_rows.append(r)
            keys.add(k)
    return sort_rows(target_rows)


def move_old_tracks(
    source_csv: Path,
    target_csv: Path,
    *,
    older_than: int = 20,
    now_year: Optional[int] = None,
    foreign_target_csv: Optional[Path] = None,
    dry_run: bool = False,
    sync: bool = False,
    source_playlist_id: Optional[str] = None,
    target_playlist_id: Optional[str] = None,
    foreign_target_playlist_id: Optional[str] = None,
    headers_path: Optional[Path] = None,
    cache_path: Path = Path("tasks/ytmusic/data/cache_mb.json"),
    log_path: Optional[Path] = None,
) -> Dict[str, int]:
    """
    从 source_csv 移出发行满 older_than 年的歌:中文歌进 target_csv,
    外文歌进 foreign_target_csv(未提供时全部进 target_csv)。
    各 CSV 按 release_date 排序,可选同步到 YT。无 release_date 的行不移动。
    """
    cutoff = compute_cutoff_date(older_than, now_year)

    src_rows = load_csv(source_csv)
    tgt_rows = load_csv(target_csv)
    foreign_rows = load_csv(foreign_target_csv) if foreign_target_csv and foreign_target_csv.exists() else []

    move_cn: List[Dict[str, str]] = []
    move_foreign: List[Dict[str, str]] = []
    remain_rows: List[Dict[str, str]] = []
    for r in src_rows:
        rd = r.get("release_date", "")
        if rd and rd <= cutoff:
            if foreign_target_csv and is_foreign(r.get("title", ""), r.get("artists", "")):
                move_foreign.append(r)
            else:
                move_cn.append(r)
        else:
            remain_rows.append(r)

    tgt_rows = _merge_into(tgt_rows, move_cn)
    if foreign_target_csv:
        foreign_rows = _merge_into(foreign_rows, move_foreign)
    remain_rows = sort_rows(remain_rows)

    if not dry_run:
        write_csv(remain_rows, source_csv)
        write_csv(tgt_rows, target_csv)
        if foreign_target_csv:
            write_csv(foreign_rows, foreign_target_csv)

    if sync and headers_path:
        sync_plan = [
            (target_csv, target_playlist_id),
            (foreign_target_csv, foreign_target_playlist_id),
            (source_csv, source_playlist_id),
        ]
        for csv_path, pid in sync_plan:
            if csv_path and pid:
                apply_csv_to_playlist(
                    headers=headers_path,
                    csv_path=csv_path,
                    playlist_id=pid,
                    cache_path=cache_path,
                    yt_limit=5,
                    log_path=Path(f"{csv_path.stem}_update.log"),
                )

    summary = {
        "moved_count": len(move_cn) + len(move_foreign),
        "moved_cn": len(move_cn),
        "moved_foreign": len(move_foreign),
        "source_count": len(remain_rows),
        "target_count": len(tgt_rows),
        "foreign_target_count": len(foreign_rows),
        "cutoff_date": cutoff,
    }
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2))

    return summary


__all__ = ["move_old_tracks", "compute_cutoff_date"]
