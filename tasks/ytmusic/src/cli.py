import argparse
import sys
from pathlib import Path
from typing import List, Sequence
from urllib.parse import parse_qs, urlparse

from tasks.ytmusic.src.ytmusic.client import DEFAULT_HEADERS_PATH, build_client
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
    move_parser.add_argument("--target-csv", type=Path, required=True, help="目标 CSV（如 local/昨日重现.csv）")
    move_parser.add_argument("--older-than", type=int, default=20, help="超过多少年算老歌，默认 20 年")
    move_parser.add_argument("--now-year", type=int, default=None, help="可指定当前年份，默认取系统年份")
    move_parser.add_argument("--dry-run", action="store_true", help="仅预览不落盘")
    move_parser.add_argument("--sync", action="store_true", help="同步更新对应的 YT 歌单")
    move_parser.add_argument("--source-playlist-id", help="源播放列表 ID（配合 --sync）")
    move_parser.add_argument("--target-playlist-id", help="目标播放列表 ID（配合 --sync）")
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


def main(argv: Sequence[str] | None = None) -> None:
    parser = create_parser()
    args = parser.parse_args(argv)

    client = build_client(args.headers)
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

            mapping = json.loads(args.playlists_json.read_text())
            src_name = args.source_csv.stem
            tgt_name = args.target_csv.stem
            if not args.source_playlist_id and src_name in mapping:
                args.source_playlist_id = mapping[src_name]
            if not args.target_playlist_id and tgt_name in mapping:
                args.target_playlist_id = mapping[tgt_name]
        moved = move_old_tracks(
            source_csv=args.source_csv,
            target_csv=args.target_csv,
            older_than=args.older_than,
            now_year=args.now_year,
            dry_run=args.dry_run,
            sync=args.sync,
            source_playlist_id=args.source_playlist_id,
            target_playlist_id=args.target_playlist_id,
            headers_path=args.headers,
            cache_path=args.cache,
            log_path=args.log,
        )
        print(f"完成移动，符合条件 {moved['moved_count']} 首，源剩余 {moved['source_count']}，目标现有 {moved['target_count']}")
    else:
        parser.error(f"未知指令: {args.command}")


if __name__ == "__main__":
    main(sys.argv[1:])
