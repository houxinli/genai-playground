#!/usr/bin/env python3
"""
Download Fanbox posts for a creator and emit Pixiv-style text/YAML files.

- Authenticates with FANBOXSESSID (CLI/env/cookie file)
- Enumerates all posts via Fanbox public API
- Writes raw JSON metadata and normalized .txt with YAML front matter + body text

Usage example:

    python fanbox_download.py --creator-id momizi813
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import requests

try:
    from bs4 import BeautifulSoup  # type: ignore
except Exception:  # pragma: no cover - optional dependency, but bundled in env
    BeautifulSoup = None

try:
    import cloudscraper
except Exception as exc:  # pragma: no cover
    raise SystemExit("cloudscraper 未安装，请在 llm 环境中安装后重试。") from exc


API_BASE = "https://api.fanbox.cc"
DEFAULT_HEADERS = {
    "User-Agent": "PixivAndroidApp/5.0.234 (Android 11; Pixel 5)",
    "Accept": "application/json",
    "Accept-Language": "ja-JP",
    "Origin": "https://app-api.pixiv.net",
    "Referer": "https://app-api.pixiv.net/",
}


def build_logger(verbose: bool) -> logging.Logger:
    logger = logging.getLogger("fanbox-download")
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(levelname)s: %(message)s")
    handler.setFormatter(formatter)
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    return logger


def read_session_from_cookie_file(cookie_path: Path) -> Optional[str]:
    """Parse FANBOXSESSID from a Netscape cookie file."""
    if not cookie_path.exists():
        return None
    for line in cookie_path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        name, value = parts[5], parts[6]
        if name == "FANBOXSESSID":
            return value.strip()
    return None


def resolve_session_id(cli_session: Optional[str], cookie_file: Optional[Path], logger: logging.Logger) -> str:
    if cli_session:
        return cli_session.strip()
    env_session = os.getenv("FANBOXSESSID") or os.getenv("FANBOX_SESSION")
    if env_session:
        return env_session.strip()
    if cookie_file:
        session = read_session_from_cookie_file(cookie_file)
        if session:
            return session
    raise SystemExit(
        "FANBOXSESSID 未提供。请通过 --session / 环境变量 FANBOXSESSID / cookie 文件提供会话。"
    )


def load_cookies_from_netscape_file(cookie_path: Path) -> List[Tuple[str, str, str, str, bool]]:
    cookies: List[Tuple[str, str, str, str, bool]] = []
    if not cookie_path or not cookie_path.exists():
        return cookies
    for line in cookie_path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        domain, _flag, path, secure_flag, _expiry, name, value = parts[:7]
        secure = secure_flag.lower() == "true"
        cookies.append((domain, path, name, value, secure))
    return cookies


def build_session(session_id: str, cookie_file: Optional[Path]) -> requests.Session:
    session = cloudscraper.create_scraper()
    session.headers.update(DEFAULT_HEADERS)
    session.cookies.set("FANBOXSESSID", session_id, domain=".fanbox.cc")
    session.headers["Cookie"] = f"FANBOXSESSID={session_id}"
    if cookie_file:
        for domain, path, name, value, secure in load_cookies_from_netscape_file(cookie_file):
            session.cookies.set(name, value, domain=domain, path=path, secure=secure)
        # Refresh raw Cookie header to include Cloudflare tokens if present
        session.headers["Cookie"] = "; ".join(
            f"{cookie.name}={cookie.value}" for cookie in session.cookies
        )
    return session


def fetch_json(
    session: requests.Session,
    url: str,
    params: Optional[Dict[str, str]] = None,
    timeout: int = 30,
    logger: Optional[logging.Logger] = None,
) -> Dict:
    resp = session.get(url, params=params, timeout=timeout)
    if resp.status_code >= 400:
        if logger:
            body_snippet = resp.text[:300]
            logger.error("HTTP %s %s params=%s body=%s", resp.status_code, resp.url, params, body_snippet)
        resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and "error" in data:
        raise RuntimeError(f"Fanbox API error: {data['error']}")
    return data


def ensure_http_scheme(url: str) -> str:
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return "https://" + url.lstrip("/")


def iterate_creator_posts(
    session: requests.Session,
    creator_id: str,
    limit: int,
    max_posts: Optional[int],
    sleep: float,
    logger: logging.Logger,
) -> Iterable[Dict]:
    session.headers["Referer"] = f"https://{creator_id}.fanbox.cc/"
    fetched = 0
    seen_post_ids = set()

    # 主路径：post.listCreator（支持 limit + nextUrl）
    page_size = max(1, min(int(limit or 50), 100))
    next_url: Optional[str] = f"{API_BASE}/post.listCreator"
    params: Optional[Dict[str, str]] = {
        "creatorId": creator_id,
        "limit": str(page_size),
        "withPinned": "true",
    }
    try:
        while next_url:
            data = fetch_json(session, next_url, params=params, logger=logger)
            body = data.get("body") or {}
            items = body.get("items") or []
            for item in items:
                post_id = str(item.get("id"))
                if post_id in seen_post_ids:
                    continue
                seen_post_ids.add(post_id)
                yield item
                fetched += 1
                if max_posts and fetched >= max_posts:
                    logger.debug("Reached max_posts=%s, stop pagination", max_posts)
                    return
            next_raw = body.get("nextUrl")
            next_url = ensure_http_scheme(next_raw) if next_raw else None
            params = None
            if next_url and sleep > 0:
                time.sleep(sleep)
        if fetched > 0:
            return
        logger.warning("post.listCreator 未返回有效结果，回退 post.paginateCreator。")
    except Exception as exc:
        logger.warning("post.listCreator 调用失败，回退 post.paginateCreator: %s", exc)

    # 回退路径：post.paginateCreator
    pagination_url = f"{API_BASE}/post.paginateCreator"
    top = fetch_json(session, pagination_url, params={"creatorId": creator_id}, logger=logger)
    page_urls = top.get("body") or []
    for url in page_urls:
        page_url = ensure_http_scheme(url)
        data = fetch_json(session, page_url, logger=logger)
        items = data.get("body") or []
        for item in items:
            post_id = str(item.get("id"))
            if post_id in seen_post_ids:
                continue
            seen_post_ids.add(post_id)
            yield item
            fetched += 1
            if max_posts and fetched >= max_posts:
                logger.debug("Reached max_posts=%s, stop pagination", max_posts)
                return
        if sleep > 0:
            time.sleep(sleep)


def fetch_post_detail(session: requests.Session, post_id: str) -> Dict:
    data = fetch_json(session, f"{API_BASE}/post.info", params={"postId": post_id})
    return data.get("body") or {}


def sanitize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text


def html_to_text(html: str) -> str:
    if not html:
        return ""
    if BeautifulSoup is None:
        return sanitize_text(html)
    soup = BeautifulSoup(html, "html5lib") if "html5lib" else BeautifulSoup(html, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text("\n")
    return sanitize_text(text)


def extract_article_blocks(body: Dict) -> str:
    blocks = body.get("blocks") or []
    lines: List[str] = []
    for block in blocks:
        block_type = block.get("type")
        if block_type in {"p", "text"}:
            txt = block.get("text") or ""
            if txt:
                lines.append(txt)
        elif block_type in {"header", "heading"}:
            txt = block.get("text") or ""
            if txt:
                lines.append(txt.upper())
        elif block_type == "image":
            caption = block.get("caption") or block.get("text") or ""
            desc = f"[image:{caption or block.get('id') or block.get('imageId', '')}]"
            lines.append(desc.strip())
        elif block_type == "file":
            filename = block.get("name") or block.get("fileId") or "attachment"
            lines.append(f"[file:{filename}]")
        elif block_type == "embed":
            service = block.get("service") or "embed"
            lines.append(f"[{service} embed]")
        elif block_type == "quote":
            txt = block.get("text") or ""
            if txt:
                lines.append(f"> {txt}")
        elif block_type == "codeBlock":
            txt = block.get("text") or ""
            if txt:
                lines.append(txt)
        else:
            raw = block.get("text") or json.dumps(block, ensure_ascii=False)
            lines.append(raw)
    if not lines and body.get("text"):
        lines.append(body["text"])
    return sanitize_text("\n\n".join(line.strip() for line in lines if line is not None))


def extract_body_text(detail: Dict) -> Tuple[str, str]:
    body = detail.get("body") or {}
    body_type = body.get("type") or detail.get("type")
    text = ""
    if body_type == "article":
        text = extract_article_blocks(body)
    elif body_type == "html":
        text = html_to_text(body.get("html") or "")
    elif body_type in {"text", "blog"}:
        text = sanitize_text(body.get("text") or "")
    elif body_type == "image":
        # No text, describe attachments
        images = body.get("images") or []
        lines = []
        for img in images:
            caption = img.get("caption") or img.get("id") or img.get("imageId", "")
            lines.append(f"[image] {caption}".strip())
        text = "\n".join(lines)
    elif body_type == "file":
        files = body.get("files") or []
        lines = []
        for fobj in files:
            name = fobj.get("name") or fobj.get("id") or "attachment"
            lines.append(f"[file] {name}".strip())
        text = "\n".join(lines)
    else:
        # Fall back to html/text fields if present
        if body.get("html"):
            text = html_to_text(body["html"])
        elif body.get("text"):
            text = sanitize_text(body["text"])
        else:
            text = json.dumps(body, ensure_ascii=False, indent=2)
    return body_type or "unknown", text.strip()


def yaml_escape(value: Optional[str]) -> str:
    if value is None:
        return ""
    return str(value).replace("\n", " ").strip()


def build_yaml_frontmatter(detail: Dict, body_type: str, creator_id: str) -> str:
    creator = (detail.get("creator") or {}) if isinstance(detail.get("creator"), dict) else {}
    tags = detail.get("tags") or []
    if isinstance(tags, dict):
        tags = tags.values()
    tags_list = [str(tag).strip() for tag in tags if str(tag).strip()]
    lines = [
        "---",
        f"post_id: {detail.get('id')}",
        f"title: {yaml_escape(detail.get('title'))}",
        f"excerpt: {yaml_escape(detail.get('excerpt'))}",
        "creator:",
        f"  id: {yaml_escape(creator.get('creatorId') or creator_id or detail.get('creatorId'))}",
        f"  name: {yaml_escape(creator.get('name'))}",
        f"fee_required: {detail.get('feeRequired')}",
        f"is_restricted: {detail.get('isRestricted')}",
        f"published_at: {yaml_escape(detail.get('publishedDatetime') or detail.get('publishedAt'))}",
        f"updated_at: {yaml_escape(detail.get('updatedDatetime') or detail.get('updatedAt'))}",
        f"body_type: {yaml_escape(body_type)}",
        "tags: [" + ", ".join(tags_list) + "]",
        f"source_url: https://{creator_id}.fanbox.cc/posts/{detail.get('id')}",
        "lang: ja",
        "---",
        "",
    ]
    return "\n".join(lines)


def write_outputs(
    detail: Dict,
    body_text: str,
    yaml_front: str,
    output_root: Path,
    logger: logging.Logger,
    save_json: bool = True,
) -> None:
    post_id = str(detail.get("id"))
    output_root.mkdir(parents=True, exist_ok=True)
    if save_json:
        meta_path = output_root / f"{post_id}.meta.json"
        meta_path.write_text(json.dumps(detail, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.debug("WRITE %s", meta_path)
    text_path = output_root / f"{post_id}.txt"
    text_path.write_text(f"{yaml_front}{body_text}\n", encoding="utf-8")
    logger.info("WRITE %s", text_path)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download all posts from a Fanbox creator.")
    translation_root = Path(__file__).resolve().parents[1]
    parser.add_argument("--creator-id", required=True, help="Fanbox creator ID, e.g. momizi813")
    parser.add_argument("--session", help="FANBOXSESSID value (optional if env/cookie file provided)")
    parser.add_argument(
        "--cookie-file",
        type=Path,
        default=translation_root / "data" / "fanbox-cookies.txt",
        help="Path to Netscape cookie file containing FANBOXSESSID",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=translation_root / "data" / "fanbox",
        help="Directory to store downloads (default: tasks/translation/data/fanbox)",
    )
    parser.add_argument("--limit", type=int, default=50, help="Pagination size per API call (default 50)")
    parser.add_argument("--max-posts", type=int, default=0, help="Optional cap on number of posts to fetch")
    parser.add_argument("--sleep", type=float, default=0.5, help="Delay between pagination calls (seconds)")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing files")
    parser.add_argument("--user-agent", help="Override default User-Agent header when calling Fanbox API")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)
    logger = build_logger(args.verbose)
    try:
        session_id = resolve_session_id(args.session, args.cookie_file, logger)
    except SystemExit as exc:
        logger.error(str(exc))
        raise

    session = build_session(session_id, args.cookie_file if args.cookie_file and args.cookie_file.exists() else None)
    if args.user_agent:
        session.headers["User-Agent"] = args.user_agent
    # Preflight visit to satisfy Cloudflare and establish session cookies
    warmup_url = f"https://{args.creator_id}.fanbox.cc/"
    try:
        warmup_resp = session.get(warmup_url, timeout=30)
        logger.debug("Warmup %s -> %s", warmup_url, warmup_resp.status_code)
        if warmup_resp.status_code >= 400:
            logger.warning("访问主页返回 %s，可能影响后续 API 调用。", warmup_resp.status_code)
    except Exception as exc:
        logger.warning("访问主页失败: %s", exc)

    output_dir = args.output_root / args.creator_id
    raw_dir = output_dir

    existing_ids = set()
    if not args.overwrite and raw_dir.exists():
        existing_ids = {path.stem for path in raw_dir.glob("*.txt")}
        if existing_ids:
            logger.info("检测到已有 %d 篇文章，将跳过重复下载（使用 --overwrite 强制重下）", len(existing_ids))

    max_posts = args.max_posts if args.max_posts > 0 else None

    fetched = 0
    for summary in iterate_creator_posts(
        session,
        creator_id=args.creator_id,
        limit=args.limit,
        max_posts=max_posts,
        sleep=args.sleep,
        logger=logger,
    ):
        post_id = str(summary.get("id"))
        if not args.overwrite and post_id in existing_ids:
            logger.debug("Skip existing post %s", post_id)
            continue
        logger.info("Fetching post %s - %s", post_id, summary.get("title"))
        detail = fetch_post_detail(session, post_id)
        if not detail:
            logger.warning("Empty detail for post %s", post_id)
            continue
        body_type, body_text = extract_body_text(detail)
        yaml_front = build_yaml_frontmatter(detail, body_type, args.creator_id)
        write_outputs(detail, body_text, yaml_front, raw_dir, logger, save_json=True)
        fetched += 1

    logger.info("完成。新下载 %d 篇文章。", fetched)


if __name__ == "__main__":
    main()
