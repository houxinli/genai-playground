"""把 paperbridge `/music/` 服务器快照拉回本地:服务器是歌单真相源(2026-11-11 起),本地 CSV 跟随。

跟随内容:
- 换版本/留空:写 CSV videoId、overrides.json(带 reason)、cache_mb.json;
- 增删移(网页上加歌、删歌、在歌单间移动):CSV 增删行;从别的歌单移来的歌沿用原来那行的其余列;
- 改日期:写 CSV release_date 和 overrides.json(本地重建时以 override 为准);
- 候选列表写 candidates.json。

网页上删掉的歌记进 `paperbridge_removed.json`(以后从 QQ 导入新歌时据此不再加回)。
本地有、服务器上没有的歌单 CSV 不动;服务器有、本地没有 CSV 的歌单只报告。
"""

from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

from tasks.ytmusic.src.ytmusic.sync_pipeline import sort_rows

from .normalize import make_key


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_csv(path: Path) -> tuple[List[str], List[Dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


def import_library(
    library: Dict[str, Any],
    *,
    playlists_json: Path,
    repo_root: Path,
    overrides_path: Path,
    cache_path: Path,
    candidates_path: Path,
    removed_path: Path | None = None,
    dry_run: bool = False,
    today: date | None = None,
) -> Dict[str, Any]:
    entries = {p["title"]: p for p in json.loads(playlists_json.read_text(encoding="utf-8"))
               if str(p.get("path", "")).endswith(".csv")}
    overrides = json.loads(overrides_path.read_text(encoding="utf-8"))
    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    candidates = json.loads(candidates_path.read_text(encoding="utf-8")) if candidates_path.exists() else {}
    removed_log = json.loads(removed_path.read_text(encoding="utf-8")) if removed_path and removed_path.exists() else []
    stamp = (today or date.today()).isoformat()

    # 先读出所有涉及的 CSV:移到别的歌单的歌要沿用原来那行(专辑、日期来源等列)。
    tables: Dict[str, tuple[Path, List[str], List[Dict[str, str]]]] = {}
    unmatched: List[str] = []
    for playlist in library["playlists"]:
        entry = entries.get(playlist["name"])
        if entry is None:
            unmatched.append(f"{playlist['name']}: 本地没有对应 CSV")
            continue
        path = repo_root / entry["path"]
        tables[playlist["name"]] = (path, *_read_csv(path))
    pool: Dict[str, Dict[str, str]] = {}
    for _, _, rows in tables.values():
        for row in rows:
            pool.setdefault(make_key(row.get("title", ""), row.get("artists", "")), row)

    changes: List[Dict[str, str]] = []
    membership: List[Dict[str, str]] = []
    for playlist in library["playlists"]:
        if playlist["name"] not in tables:
            continue
        path, fieldnames, rows = tables[playlist["name"]]
        original = [dict(row) for row in rows]  # 行会被就地改写，留一份原样用来判断要不要写回
        local: Dict[str, Dict[str, str]] = {}
        for row in rows:
            key = make_key(row.get("title", ""), row.get("artists", ""))
            if key in local:
                membership.append({"op": "duplicate", "playlist": playlist["name"], "key": key})
            else:
                local[key] = row
        server_keys = {t["key"] for t in playlist["tracks"]}

        new_rows: List[Dict[str, str]] = []
        for track in playlist["tracks"]:
            key = track["key"]
            row = local.get(key)
            if row is None:
                source = pool.get(key)
                row = dict(source) if source else {name: "" for name in fieldnames}
                if not source:
                    row.update(source="paperbridge", note="网页上添加")
                membership.append({"op": "move_in" if source else "add", "playlist": playlist["name"], "key": key})
                if not source:
                    overrides[key] = {**overrides.get(key, {}), "reason": f"{stamp} paperbridge 网页添加"}
            row["title"] = track.get("title") or row.get("title", "")
            row["artists"] = track.get("artists", row.get("artists", ""))

            new_id = track.get("video_id") or ""
            if new_id != (row.get("videoId") or ""):
                if key in local:
                    changes.append({"playlist": playlist["name"], "key": key, "from": row.get("videoId") or "", "to": new_id})
                row["videoId"] = new_id
                label = (track.get("current") or {}).get("label", "")
                reason = f"{stamp} paperbridge 网页选版同步" + (f": {label}" if label else (": 留空" if not new_id else ""))
                overrides[key] = {**overrides.get(key, {}), "videoId": new_id, "reason": reason}
                cache.setdefault(key, {}).setdefault("yt", {})["videoId"] = new_id

            new_date = track.get("release_date") or ""
            if new_date and new_date != (row.get("release_date") or ""):
                if key in local or key in pool:
                    membership.append({"op": "date", "playlist": playlist["name"], "key": key,
                                       "from": row.get("release_date") or "", "to": new_date})
                row["release_date"] = new_date
                previous = overrides.get(key, {})
                overrides[key] = {**previous, "release_date": new_date,
                                  "reason": previous.get("reason") if previous.get("reason", "").startswith(stamp)
                                  else f"{stamp} paperbridge 网页改日期"}

            if track.get("candidates") or track.get("current"):
                entry_out: Dict[str, Any] = {"candidates": track.get("candidates", [])}
                for field in ("ref_length_s", "note"):
                    if track.get(field):
                        entry_out[field] = track[field]
                if track.get("current"):
                    entry_out["current"] = {k: v for k, v in track["current"].items() if k != "video_id"}
                candidates.setdefault(playlist["name"], {})[key] = entry_out
            new_rows.append(row)

        for key in local:
            if key in server_keys:
                continue
            moved_to = next((p["name"] for p in library["playlists"] if p is not playlist
                             and any(t["key"] == key for t in p["tracks"])), None)
            if moved_to:
                membership.append({"op": "move_out", "playlist": playlist["name"], "key": key, "to": moved_to})
            else:
                membership.append({"op": "remove", "playlist": playlist["name"], "key": key})
                removed_log.append({"playlist": playlist["name"], "key": key, "at": stamp})
            candidates.get(playlist["name"], {}).pop(key, None)

        new_rows = sort_rows(new_rows)
        if new_rows != original and not dry_run:
            with path.open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(new_rows)
    if not dry_run:
        _write_json(overrides_path, overrides)
        _write_json(cache_path, cache)
        _write_json(candidates_path, candidates)
        if removed_path:
            _write_json(removed_path, removed_log)
    return {"changes": changes, "membership": membership, "unmatched": unmatched}


__all__ = ["import_library"]
