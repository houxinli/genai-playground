"""把 paperbridge `/music/` 服务器快照拉回本地:网页同步后服务器是真相源,本地 CSV 跟随。

只同步 videoId(换版本/留空)与候选列表;不增删 CSV 行(增删歌仍走本地管线),
两边对不上的曲目只报告。每处 videoId 修改同时写 CSV、overrides.json(带 reason)、cache_mb.json。
"""

from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

from .normalize import make_key


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def import_library(
    library: Dict[str, Any],
    *,
    playlists_json: Path,
    repo_root: Path,
    overrides_path: Path,
    cache_path: Path,
    candidates_path: Path,
    dry_run: bool = False,
    today: date | None = None,
) -> Dict[str, Any]:
    entries = {p["title"]: p for p in json.loads(playlists_json.read_text(encoding="utf-8"))
               if str(p.get("path", "")).endswith(".csv")}
    overrides = json.loads(overrides_path.read_text(encoding="utf-8"))
    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    candidates = json.loads(candidates_path.read_text(encoding="utf-8")) if candidates_path.exists() else {}
    stamp = (today or date.today()).isoformat()

    changes: List[Dict[str, str]] = []
    unmatched: List[str] = []
    for playlist in library["playlists"]:
        entry = entries.get(playlist["name"])
        if entry is None:
            unmatched.append(f"{playlist['name']}: 本地没有对应 CSV")
            continue
        csv_path = repo_root / entry["path"]
        with csv_path.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            fieldnames = list(reader.fieldnames or [])
            rows = list(reader)
        server = {t["key"]: t for t in playlist["tracks"]}
        local_keys = set()
        changed = False
        for row in rows:
            key = make_key(row.get("title", ""), row.get("artists", ""))
            local_keys.add(key)
            track = server.get(key)
            if track is None:
                continue
            new_id = track.get("video_id") or ""
            if new_id != (row.get("videoId") or ""):
                changes.append({"playlist": playlist["name"], "key": key, "from": row.get("videoId") or "", "to": new_id})
                row["videoId"] = new_id
                changed = True
                label = (track.get("current") or {}).get("label", "")
                reason = f"{stamp} paperbridge 网页选版同步" + (f": {label}" if label else ": 留空")
                overrides[key] = {**overrides.get(key, {}), "videoId": new_id, "reason": reason}
                cache.setdefault(key, {}).setdefault("yt", {})["videoId"] = new_id
            if track.get("candidates") or track.get("current"):
                entry_out: Dict[str, Any] = {"candidates": track.get("candidates", [])}
                for field in ("ref_length_s", "note"):
                    if track.get(field):
                        entry_out[field] = track[field]
                if track.get("current"):
                    entry_out["current"] = {k: v for k, v in track["current"].items() if k != "video_id"}
                candidates.setdefault(playlist["name"], {})[key] = entry_out
        unmatched += [f"{playlist['name']}: 服务器有、本地没有 {k}" for k in server if k not in local_keys]
        if changed and not dry_run:
            with csv_path.open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
    if not dry_run:
        _write_json(overrides_path, overrides)
        _write_json(cache_path, cache)
        _write_json(candidates_path, candidates)
    return {"changes": changes, "unmatched": unmatched}


__all__ = ["import_library"]
