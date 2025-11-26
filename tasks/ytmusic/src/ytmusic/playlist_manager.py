from typing import Any, Dict, List, Optional, Sequence

from ytmusicapi import YTMusic


class PlaylistManager:
    """封装播放列表的基本操作。"""

    def __init__(self, client: YTMusic) -> None:
        self.client = client

    def list_playlists(self, limit: Optional[int] = 50) -> List[Dict]:
        """返回当前账号的播放列表信息。"""
        return self.client.get_library_playlists(limit=limit)

    def create_playlist(
        self,
        name: str,
        description: str = "",
        privacy: str = "PRIVATE",
    ) -> str:
        """创建播放列表并返回 playlist id。"""
        return self.client.create_playlist(
            name,
            description,
            privacy_status=privacy,
        )

    def add_tracks(self, playlist_id: str, video_ids: List[str]) -> Dict:
        """向播放列表添加歌曲。空列表时返回 no-op 结果。"""
        if not video_ids:
            return {"status": "noop", "playlistId": playlist_id}
        return self.client.add_playlist_items(playlist_id, video_ids)

    def get_playlist_tracks(self, playlist_id: str, limit: Optional[int] = 100) -> Dict[str, Any]:
        """获取播放列表详情和曲目列表。"""
        playlist = self.client.get_playlist(playlist_id, limit=limit)
        tracks = playlist.get("tracks", [])
        track_count = playlist.get("trackCount")
        return {
            "id": playlist_id,
            "title": playlist.get("title", ""),
            "trackCount": track_count,
            "tracks": tracks,
        }

    def find_tracks_by_title(
        self,
        playlist_id: str,
        title: str,
        limit: Optional[int] = 200,
    ) -> List[Dict[str, Any]]:
        """按标题匹配（忽略大小写/首尾空格），返回匹配到的曲目列表。"""
        playlist = self.get_playlist_tracks(playlist_id, limit=limit)
        target = title.strip().lower()
        matches = []
        for track in playlist.get("tracks", []):
            track_title = (track.get("title") or "").strip().lower()
            if track_title == target:
                matches.append(track)
        return matches

    def remove_playlist_items(self, playlist_id: str, items: Sequence[Dict[str, Any]]) -> Dict:
        """调用 API 删除播放列表中的指定条目（需包含 setVideoId 或 videoId）。"""
        return self.client.remove_playlist_items(playlist_id, list(items))
