from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from tasks.ytmusic.src.core.cache_utils import SongCache
from tasks.ytmusic.src.ytmusic.sync_pipeline import apply_csv_to_playlist, sort_rows


def parse_year(val: str) -> Optional[int]:
    if not val:
        return None
    try:
        return int(str(val).split("-")[0])
    except Exception:
        return None


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


def move_old_tracks(
    source_csv: Path,
    target_csv: Path,
    *,
    older_than: int = 20,
    now_year: Optional[int] = None,
    dry_run: bool = False,
    sync: bool = False,
    source_playlist_id: Optional[str] = None,
    target_playlist_id: Optional[str] = None,
    headers_path: Optional[Path] = None,
    cache_path: Path = Path("tasks/ytmusic/data/cache_mb.json"),
    log_path: Optional[Path] = None,
    yt_client_factory=None,
) -> Dict[str, int]:
    """
    从 source_csv 中筛选发行日期早于 now_year-older_than 的歌曲，移到 target_csv。
    重新按 release_date 排序，并可选同步到 YT。
    """
    now_year = now_year or datetime.now().year
    cutoff = now_year - older_than

    src_rows = load_csv(source_csv)
    tgt_rows = load_csv(target_csv)

    def key_fn(r: Dict[str, str]) -> str:
        return (r.get("title", "") + "|" + r.get("artists", "")).strip()

    move_rows: List[Dict[str, str]] = []
    remain_rows: List[Dict[str, str]] = []
    for r in src_rows:
        y = parse_year(r.get("release_date", ""))
        if y is not None and y <= cutoff:
            move_rows.append(r)
        else:
            remain_rows.append(r)

    tgt_keys = {key_fn(r) for r in tgt_rows}
    for r in move_rows:
        k = key_fn(r)
        if k not in tgt_keys:
            tgt_rows.append(r)
            tgt_keys.add(k)

    tgt_rows = sort_rows(tgt_rows)
    remain_rows = sort_rows(remain_rows)

    if not dry_run:
        write_csv(remain_rows, source_csv)
        write_csv(tgt_rows, target_csv)

    if sync and headers_path and target_playlist_id:
        yt = yt_client_factory() if yt_client_factory else None
        apply_csv_to_playlist(
            headers=headers_path if yt is None else headers_path,
            csv_path=target_csv,
            playlist_id=target_playlist_id,
            cache_path=cache_path,
            yt_limit=5,
            search_missing=False,
            log_path=Path(f"{target_csv.stem}_update.log"),
        )
        if source_playlist_id:
            apply_csv_to_playlist(
                headers=headers_path,
                csv_path=source_csv,
                playlist_id=source_playlist_id,
                cache_path=cache_path,
                yt_limit=5,
                search_missing=False,
                log_path=Path(f"{source_csv.stem}_update.log"),
            )

    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        summary = {
            "moved": len(move_rows),
            "source_after": len(remain_rows),
            "target_after": len(tgt_rows),
            "cutoff_year": cutoff,
        }
        log_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2))

    return {
        "moved_count": len(move_rows),
        "source_count": len(remain_rows),
        "target_count": len(tgt_rows),
    }


__all__ = ["move_old_tracks"]
