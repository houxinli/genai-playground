import argparse
import sys
from pathlib import Path
from typing import List, Sequence

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
    else:
        parser.error(f"未知指令: {args.command}")


if __name__ == "__main__":
    main(sys.argv[1:])
