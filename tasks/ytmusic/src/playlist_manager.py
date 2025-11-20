from typing import Any, Dict, List, Optional

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
