"""歌单审计与选版打分。

审计:逐首核对 CSV 里的 videoId 在 YT 上实际是什么,标记
no_videoId / unavailable / bad_keyword(live、remix、伴奏等) / title_mismatch /
artist_mismatch / duration_gap(与 QQ 原曲时长差 >25s)。

选版:从搜索候选里挑最像原唱首发版的——歌手匹配(含中英艺名对照)、
标题匹配(繁简归一后模糊比对)、时长贴近 QQ 原曲、坏关键词与串烧标题扣分。
达不到置信阈值返回 None,留给人工。
"""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from tasks.ytmusic.src.core.normalize import make_key, normalize_artists

try:
    from zhconv import convert as _zh_convert
except ImportError:  # pragma: no cover
    _zh_convert = None

ALIASES_PATH = Path(__file__).with_name("artist_aliases.json")

BAD_LATIN = ["remix", "remaster", "cover", "instrumental", "karaoke", "acoustic",
             "nightcore", "sped up", "slowed", "reverb", "mashup", "medley", "live"]
BAD_CJK = ["伴奏", "翻唱", "纯音乐", "钢琴版", "串烧", "混音", "现场", "演唱会", "改编", "抒情版", "新版", "重录"]

DEFAULT_PICK_THRESHOLD = 120


def load_aliases(path: Path = ALIASES_PATH) -> Dict[str, str]:
    data = json.loads(path.read_text())
    return {k: v for k, v in data.items() if not k.startswith("_")}


def simp(text: str) -> str:
    text = (text or "").lower()
    return _zh_convert(text, "zh-cn") if _zh_convert else text


def clean(text: str) -> str:
    text = simp(text)
    text = re.sub(r"[\(\[（【].*?[\)\]）】]", " ", text)
    return re.sub(r"[^0-9a-z一-鿿가-힯぀-ヿ]+", "", text)


def bad_hits(candidate_title: str, expected_title: str) -> List[str]:
    a, e = simp(candidate_title), simp(expected_title)
    hits = [w for w in BAD_LATIN if re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", a) and w not in e]
    hits += [w for w in BAD_CJK if w in a and w not in e]
    # 串烧标题(如"流沙+天天"),先去掉括号内容再看正文里的 + 或 /
    stripped = re.sub(r"[\(\[（【].*?[\)\]）】]", "", candidate_title or "")
    if re.search(r"[+/]", stripped) and not re.search(r"[+/]", expected_title or ""):
        hits.append("medley_title")
    return hits


def artist_match(expected_artist: str, candidate_names: Sequence[str], aliases: Dict[str, str]) -> bool:
    ea = clean(expected_artist)
    names = [clean(n) for n in candidate_names if n]
    if any(ea and n and (ea in n or n in ea) for n in names):
        return True
    alias = aliases.get(expected_artist.strip())
    return bool(alias and any(alias in n or n in alias for n in names))


def title_match(expected: str, candidate: str) -> bool:
    et, ct = clean(expected), clean(candidate)
    return bool(et and ct and (et == ct or et in ct or ct in et
                               or SequenceMatcher(None, et, ct).ratio() > 0.75))


def score_candidate(
    candidate: Dict[str, Any],
    expected_title: str,
    expected_artist: str,
    qq_len: Optional[int],
    aliases: Dict[str, str],
) -> int:
    names = [a.get("name", "") for a in candidate.get("artists", []) or []]
    score = 100 if artist_match(expected_artist, names, aliases) else -50
    score += 50 if title_match(expected_title, candidate.get("title", "")) else -30
    score -= 80 * len(bad_hits(candidate.get("title", ""), expected_title))
    duration = candidate.get("duration_seconds") or 0
    if qq_len and duration:
        diff = abs(duration - qq_len)
        if diff <= 12:
            score += 40
        elif diff <= 25:
            score += 15
        elif diff > 60:
            score -= 40
        else:
            score -= 10
    return score


def pick_video(
    search_fn: Callable[[str], List[Dict[str, Any]]],
    title: str,
    artists: str,
    qq_len: Optional[int] = None,
    *,
    aliases: Optional[Dict[str, str]] = None,
    threshold: int = DEFAULT_PICK_THRESHOLD,
) -> Optional[Dict[str, Any]]:
    """search_fn 接收查询串返回候选列表;返回带 _score 的最佳候选或 None。"""
    aliases = aliases if aliases is not None else load_aliases()
    expected_artist = normalize_artists(artists)
    best, best_score = None, -999
    for cand in search_fn(f"{title} {expected_artist}".strip()) or []:
        if not cand.get("videoId"):
            continue
        s = score_candidate(cand, title, expected_artist, qq_len, aliases)
        if s > best_score:
            best, best_score = cand, s
    if best is None or best_score < threshold:
        return None
    return {**best, "_score": best_score}


def audit_row(
    row: Dict[str, str],
    video_info: Optional[Dict[str, Any]],
    qq_len: Optional[int],
    aliases: Dict[str, str],
) -> Dict[str, Any]:
    """核对一行 CSV。video_info 是 get_song 的精简结果
    {actual_title, author, length, status},videoId 为空时传 None。"""
    entry: Dict[str, Any] = {
        "title": row.get("title", ""),
        "artists": row.get("artists", ""),
        "videoId": row.get("videoId", ""),
        "flags": [],
        "detail": video_info or {},
    }
    if not row.get("videoId"):
        entry["flags"].append("no_videoId")
        return entry
    if video_info is None:
        entry["flags"].append("fetch_error")
        return entry

    actual_title = video_info.get("actual_title", "")
    status = video_info.get("status", "")
    if status not in ("OK", ""):
        entry["flags"].append(f"unavailable:{status}")

    hits = bad_hits(actual_title, row.get("title", ""))
    if hits:
        entry["flags"].append("bad_keyword:" + ",".join(hits))

    if not title_match(row.get("title", ""), actual_title):
        entry["flags"].append("title_mismatch")

    author = re.sub(r"\s*-\s*topic\s*$", "", video_info.get("author", "") or "", flags=re.I)
    if not artist_match(normalize_artists(row.get("artists", "")), [author], aliases):
        entry["flags"].append("artist_mismatch")

    length = video_info.get("length") or 0
    if qq_len and length and abs(length - qq_len) > 25:
        entry["flags"].append(f"duration_gap:{length}s_vs_qq{qq_len}s")
    return entry


def audit_playlist(
    rows: Sequence[Dict[str, str]],
    get_song_fn: Callable[[str], Optional[Dict[str, Any]]],
    qq_intervals: Optional[Dict[str, int]] = None,
    *,
    aliases: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """get_song_fn(videoId) -> {actual_title, author, length, status} 或 None(查询失败)。"""
    aliases = aliases if aliases is not None else load_aliases()
    qq_intervals = qq_intervals or {}
    report = []
    for row in rows:
        vid = row.get("videoId", "")
        info = get_song_fn(vid) if vid else None
        qq_len = qq_intervals.get(make_key(row.get("title", ""), row.get("artists", "")))
        report.append(audit_row(row, info, qq_len, aliases))
    return report


__all__ = [
    "audit_playlist", "audit_row", "pick_video", "score_candidate",
    "artist_match", "title_match", "bad_hits", "load_aliases", "clean", "simp",
]
