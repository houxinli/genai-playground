"""YTMusic 客户端构建入口。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .auth import build_from_headers, build_from_oauth

DEFAULT_HEADERS_PATH = Path(__file__).resolve().parents[2] / "config" / "headers_auth.json"
DEFAULT_OAUTH_TOKEN_PATH = Path(__file__).resolve().parents[2] / "config" / "oauth.json"
DEFAULT_OAUTH_CLIENT_PATH = Path(__file__).resolve().parents[2] / "config" / "oauth_client_current.json"


def get_client(
    auth_mode: str = "headers",
    *,
    headers_path: Optional[Path] = None,
    oauth_token_path: Optional[Path] = None,
    oauth_client_path: Optional[Path] = None,
):
    """
    构建 YTMusic 客户端。
    auth_mode: "headers" 或 "oauth"
    """
    if auth_mode not in {"headers", "oauth"}:
        raise ValueError("auth_mode 必须为 headers 或 oauth")

    if auth_mode == "headers":
        path = headers_path or DEFAULT_HEADERS_PATH
        return build_from_headers(path)

    token = oauth_token_path or DEFAULT_OAUTH_TOKEN_PATH
    client = oauth_client_path or DEFAULT_OAUTH_CLIENT_PATH
    return build_from_oauth(token, client)


__all__ = ["get_client", "DEFAULT_HEADERS_PATH", "DEFAULT_OAUTH_TOKEN_PATH", "DEFAULT_OAUTH_CLIENT_PATH"]
