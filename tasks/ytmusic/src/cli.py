import argparse
import sys
from pathlib import Path
from typing import List, Sequence
from urllib.parse import parse_qs, urlparse

from client import DEFAULT_HEADERS_PATH, build_client
from playlist_manager import PlaylistManager


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
    else:
        parser.error(f"未知指令: {args.command}")


if __name__ == "__main__":
    main(sys.argv[1:])
