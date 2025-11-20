from pathlib import Path
from typing import Optional, Union

from ytmusicapi import YTMusic


DEFAULT_HEADERS_PATH = Path(__file__).resolve().parent.parent / "config" / "headers_auth.json"


def resolve_headers_path(headers_path: Optional[Union[str, Path]]) -> Path:
    """
    Resolve the headers path, defaulting to the shared config location.
    Raises FileNotFoundError if the file is missing so the caller can surface
    a clear setup error.
    """
    resolved = Path(headers_path).expanduser() if headers_path else DEFAULT_HEADERS_PATH
    if not resolved.exists():
        raise FileNotFoundError(f"找不到认证头文件: {resolved}")
    return resolved


def build_client(headers_path: Optional[Union[str, Path]] = None) -> YTMusic:
    """Create a YTMusic client pointing at the desired headers file."""
    resolved_path = resolve_headers_path(headers_path)
    return YTMusic(resolved_path)
