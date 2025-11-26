import json
from pathlib import Path
from typing import Any, Dict, Optional


class SongCache:
    """
    简单的文件缓存，按 key(title|artists) 存储各平台信息，避免重复请求。
    结构示例：
    {
      "title|artists": {
        "mb": {"release_date": "2005-01-01", "raw": {...}},
        "yt": {"videoId": "abc", "album_year": "2003"},
        "qq": {...}
      },
      ...
    }
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.data: Dict[str, Dict[str, Any]] = {}
        if path.exists():
            try:
                self.data = json.loads(path.read_text())
            except Exception:
                self.data = {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2))

    def get(self, key: str, platform: str, field: str) -> Optional[Any]:
        return self.data.get(key, {}).get(platform, {}).get(field)

    def set(self, key: str, platform: str, field: str, value: Any) -> None:
        self.data.setdefault(key, {}).setdefault(platform, {})[field] = value

    def set_raw(self, key: str, platform: str, raw: Any) -> None:
        self.data.setdefault(key, {})[platform] = raw

    def has(self, key: str, platform: str, field: str) -> bool:
        return key in self.data and platform in self.data[key] and field in self.data[key][platform]
