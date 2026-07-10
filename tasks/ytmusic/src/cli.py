import argparse
import sys
from pathlib import Path
from typing import List, Sequence
from urllib.parse import parse_qs, urlparse

from tasks.ytmusic.src.ytmusic.client import DEFAULT_HEADERS_PATH, get_client
from tasks.ytmusic.src.ytmusic.playlist_manager import PlaylistManager
from tasks.ytmusic.src.core.move_old_tracks import move_old_tracks


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("必须是正整数")
    return parsed


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--headers",
        type=Path,
        default=None,
        help=f"headers_auth.json 路径，默认 {DEFAULT_HEADERS_PATH}",
    )


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="管理 YouTube Music 播放列表的简易 CLI")
    add_common_args(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="列出当前账号的播放列表")
    list_parser.add_argument(
        "--limit",
        type=positive_int,
        default=50,
        help="最多返回多少条播放列表，默认 50",
    )

    create_parser = subparsers.add_parser("create", help="创建新的播放列表")
    create_parser.add_argument("--name", required=True, help="播放列表名称")
    create_parser.add_argument("--description", default="", help="描述")
    create_parser.add_argument(
        "--privacy",
        default="PRIVATE",
        choices=["PRIVATE", "PUBLIC", "UNLISTED"],
        help="可见性，默认 PRIVATE",
    )

    add_parser = subparsers.add_parser("add", help="向播放列表添加歌曲")
    add_parser.add_argument("--playlist-id", required=True, help="目标播放列表 ID")
    add_parser.add_argument(
        "--video-ids",
        nargs="+",
        required=True,
        help="要添加的歌曲/视频 ID，来自 YouTube Music/YouTube 的视频 ID",
    )

    items_parser = subparsers.add_parser("items", help="获取播放列表的曲目列表")
    items_parser.add_argument("--playlist-id", help="播放列表 ID（URL 中的 list 参数）")
    items_parser.add_argument("--url", help="播放列表 URL，会自动解析出 list 参数")
    items_parser.add_argument(
        "--limit",
        type=positive_int,
        default=200,
        help="最多拉取多少首，默认 200",
    )

    remove_parser = subparsers.add_parser("remove", help="从播放列表删除曲目")
    remove_parser.add_argument("--playlist-id", help="播放列表 ID")
    remove_parser.add_argument("--url", help="播放列表 URL，会自动解析出 list 参数")
    remove_parser.add_argument(
        "--title",
        help="要删除的歌曲标题（精确匹配，不区分大小写）。如有多首同名将全部删除。",
    )
    remove_parser.add_argument(
        "--limit",
        type=positive_int,
        default=500,
        help="扫描播放列表的最大曲目数，默认 500",
    )

    move_parser = subparsers.add_parser("move-old", help="将 source CSV 中超过指定年限的歌曲移到 target CSV/歌单")
    move_parser.add_argument("--source-csv", type=Path, required=True, help="源 CSV（如 local/not_yet.csv）")
    move_parser.add_argument("--target-csv", type=Path, required=True, help="目标 CSV（中文歌去向，如 local/昨日重现.csv）")
    move_parser.add_argument(
        "--foreign-target-csv",
        type=Path,
        default=None,
        help="外文歌（日/韩/西文）的目标 CSV，如 local/Yesterday_once_more.csv；不给则不分流",
    )
    move_parser.add_argument("--older-than", type=int, default=20, help="满多少年算老歌，默认 20 年（精确到天）")
    move_parser.add_argument("--now-year", type=int, default=None, help="指定当前年份（按年粒度），默认按今天精确到天")
    move_parser.add_argument("--dry-run", action="store_true", help="仅预览不落盘")
    move_parser.add_argument("--sync", action="store_true", help="同步更新对应的 YT 歌单")
    move_parser.add_argument("--source-playlist-id", help="源播放列表 ID（配合 --sync）")
    move_parser.add_argument("--target-playlist-id", help="目标播放列表 ID（配合 --sync）")
    move_parser.add_argument("--foreign-target-playlist-id", help="外文目标播放列表 ID（配合 --sync）")
    move_parser.add_argument("--cache", type=Path, default=Path("tasks/ytmusic/data/cache_mb.json"), help="缓存路径")
    move_parser.add_argument(
        "--log",
        type=Path,
        default=Path("tasks/ytmusic/logs/move_old.log"),
        help="变更日志路径",
    )
    move_parser.add_argument(
        "--playlists-json",
        type=Path,
        default=Path("tasks/ytmusic/data/local/playlists.json"),
        help="保存歌单名->playlistId 映射的 JSON，供 --sync 自动填充",
    )

    audit_parser = subparsers.add_parser("audit", help="逐首核对 CSV 中的 videoId 在 YT 上实际是什么")
    audit_parser.add_argument("--csv", type=Path, required=True, help="本地歌单 CSV(如 local/昨日重现.csv)")
    audit_parser.add_argument("--qq-csv", type=Path, default=None, help="对应的 QQ 导出 CSV,提供原曲时长用于比对")
    audit_parser.add_argument("--report", type=Path, required=True, help="审计报告输出路径(NDJSON)")
    audit_parser.add_argument(
        "--snapshot",
        type=Path,
        default=None,
        help="videoId->视频信息 的缓存 JSON,重跑时避免重复请求",
    )

    pull_parser = subparsers.add_parser("pull-qq", help="拉取 QQ 音乐线上歌单并写成导出格式 CSV")
    pull_parser.add_argument("--playlist-id", required=True, help="QQ 歌单 id(分享链接里的 id 参数)")
    pull_parser.add_argument("--out", type=Path, required=True, help="输出 CSV 路径(data/qqmusic/ 下)")

    return parser


def print_playlists(playlists: List[dict]) -> None:
    if not playlists:
        print("没有找到播放列表")
        return
    for entry in playlists:
        playlist_id = entry.get("playlistId") or entry.get("id") or "<unknown>"
        title = entry.get("title") or "<untitled>"
        count = entry.get("count", "?")
        print(f"- {title} | 曲目数: {count} | id: {playlist_id}")


def extract_playlist_id(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.query:
        query = parse_qs(parsed.query)
        if "list" in query and query["list"]:
            return query["list"][0]
    # 有些链接可能把 id 放在路径最后
    path_parts = [p for p in parsed.path.split("/") if p]
    if path_parts:
        last = path_parts[-1]
        if last.startswith("PL"):
            return last
    return None


def print_tracks(playlist_title: str, tracks: List[dict]) -> None:
    if not tracks:
        print(f"播放列表「{playlist_title}」为空")
        return
    for idx, track in enumerate(tracks, start=1):
        title = track.get("title") or "<untitled>"
        artists_list = track.get("artists") or []
        artists = ", ".join(a.get("name", "?") for a in artists_list) or "?"
        album_info = track.get("album") or {}
        album = album_info.get("name") if isinstance(album_info, dict) else ""
        print(f"{idx:02d}. {title} - {artists}{f' | {album}' if album else ''}")


def run_audit(args: argparse.Namespace) -> None:
    import csv
    import json
    import time

    from tasks.ytmusic.src.core.normalize import make_key, normalize_artists, normalize_title
    from tasks.ytmusic.src.ytmusic.audit import audit_playlist

    rows = list(csv.DictReader(args.csv.open()))
    qq_intervals = {}
    if args.qq_csv and args.qq_csv.exists():
        for r in csv.DictReader(args.qq_csv.open()):
            k = make_key(normalize_title(r.get("title", "")), normalize_artists(r.get("artists", "")))
            if r.get("interval_seconds"):
                qq_intervals[k] = int(r["interval_seconds"])

    snapshot = {}
    if args.snapshot and args.snapshot.exists():
        snapshot = json.loads(args.snapshot.read_text())
    yt = get_client("headers", headers_path=args.headers)

    def get_song(video_id: str):
        if video_id in snapshot:
            return snapshot[video_id]
        try:
            song = yt.get_song(video_id)
        except Exception:  # noqa: BLE001
            return None
        vd = song.get("videoDetails", {}) or {}
        info = {
            "actual_title": vd.get("title", ""),
            "author": vd.get("author", ""),
            "length": int(vd.get("lengthSeconds") or 0),
            "status": (song.get("playabilityStatus", {}) or {}).get("status", ""),
        }
        snapshot[video_id] = info
        time.sleep(0.05)
        return info

    report = audit_playlist(rows, get_song, qq_intervals)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("w", encoding="utf-8") as f:
        for e in report:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    if args.snapshot:
        args.snapshot.parent.mkdir(parents=True, exist_ok=True)
        args.snapshot.write_text(json.dumps(snapshot, ensure_ascii=False))

    flagged = [e for e in report if e["flags"]]
    counts: dict = {}
    for e in flagged:
        for fl in e["flags"]:
            counts[fl.split(":")[0]] = counts.get(fl.split(":")[0], 0) + 1
    print(f"共 {len(report)} 首, 有问题 {len(flagged)} 首 -> {args.report}")
    print(json.dumps(counts, ensure_ascii=False))


def run_pull_qq(args: argparse.Namespace) -> None:
    from tasks.ytmusic.src.qqmusic.qq_playlist_fetcher import fetch_playlist_raw, parse_playlist, write_qq_csv

    parsed = parse_playlist(fetch_playlist_raw(args.playlist_id))
    write_qq_csv(parsed["songs"], args.out)
    print(f"歌单「{parsed['name']}」共 {len(parsed['songs'])} 首 -> {args.out}")


def main(argv: Sequence[str] | None = None) -> None:
    parser = create_parser()
    args = parser.parse_args(argv)

    if args.command == "audit":
        run_audit(args)
        return
    if args.command == "pull-qq":
        run_pull_qq(args)
        return

    client = get_client("headers", headers_path=args.headers)
    manager = PlaylistManager(client)

    if args.command == "list":
        playlists = manager.list_playlists(limit=args.limit)
        print_playlists(playlists)
    elif args.command == "create":
        playlist_id = manager.create_playlist(args.name, args.description, args.privacy)
        print(f"创建成功，playlist id: {playlist_id}")
    elif args.command == "add":
        result = manager.add_tracks(args.playlist_id, args.video_ids)
        status = result.get("status") or "unknown"
        print(f"添加结果: {status} -> {result}")
    elif args.command == "items":
        playlist_id = args.playlist_id
        if not playlist_id:
            if not args.url:
                parser.error("必须提供 --playlist-id 或者 --url")
            playlist_id = extract_playlist_id(args.url)
            if not playlist_id:
                parser.error("无法从 URL 解析出 playlist id")
        playlist = manager.get_playlist_tracks(playlist_id, limit=args.limit)
        title = playlist.get("title") or playlist_id
        tracks = playlist.get("tracks", [])
        print_tracks(title, tracks)
    elif args.command == "remove":
        playlist_id = args.playlist_id
        if not playlist_id:
            if not args.url:
                parser.error("必须提供 --playlist-id 或者 --url")
            playlist_id = extract_playlist_id(args.url)
            if not playlist_id:
                parser.error("无法从 URL 解析出 playlist id")

        if not args.title:
            parser.error("当前删除命令需要提供 --title")

        matches = manager.find_tracks_by_title(playlist_id, args.title, limit=args.limit)
        if not matches:
            print(f"未找到标题为「{args.title}」的曲目")
            return
        items = []
        for track in matches:
            if track.get("setVideoId"):
                entry = {"setVideoId": track["setVideoId"]}
                if track.get("videoId"):
                    entry["videoId"] = track["videoId"]
                items.append(entry)
        if not items:
            print(f"找到 {len(matches)} 条同名曲目，但缺少必要的 setVideoId/videoId 字段，未执行删除")
            return
        result = manager.remove_playlist_items(playlist_id, items)
        print(f"删除请求已发送，匹配 {len(matches)} 条，提交 {len(items)} 条 -> {result}")
    elif args.command == "move-old":
        if args.sync and args.playlists_json.exists():
            import json

            raw = json.loads(args.playlists_json.read_text())
            # 新格式是 [{title,id,path}] 列表,旧格式是 {title: id} 字典
            if isinstance(raw, list):
                mapping = {e.get("title", ""): e.get("id", "") for e in raw}
            else:
                mapping = raw

            def lookup(stem: str) -> str | None:
                # CSV 文件名用下划线,歌单名用空格
                return mapping.get(stem) or mapping.get(stem.replace("_", " "))

            if not args.source_playlist_id:
                args.source_playlist_id = lookup(args.source_csv.stem)
            if not args.target_playlist_id:
                args.target_playlist_id = lookup(args.target_csv.stem)
            if args.foreign_target_csv and not args.foreign_target_playlist_id:
                args.foreign_target_playlist_id = lookup(args.foreign_target_csv.stem)
        moved = move_old_tracks(
            source_csv=args.source_csv,
            target_csv=args.target_csv,
            older_than=args.older_than,
            now_year=args.now_year,
            foreign_target_csv=args.foreign_target_csv,
            dry_run=args.dry_run,
            sync=args.sync,
            source_playlist_id=args.source_playlist_id,
            target_playlist_id=args.target_playlist_id,
            foreign_target_playlist_id=args.foreign_target_playlist_id,
            headers_path=args.headers,
            cache_path=args.cache,
            log_path=args.log,
        )
        print(
            f"完成移动(截止 {moved['cutoff_date']}): 中文 {moved['moved_cn']} 首, 外文 {moved['moved_foreign']} 首; "
            f"源剩余 {moved['source_count']}, 中文目标 {moved['target_count']}, 外文目标 {moved['foreign_target_count']}"
        )
    else:
        parser.error(f"未知指令: {args.command}")


if __name__ == "__main__":
    main(sys.argv[1:])
