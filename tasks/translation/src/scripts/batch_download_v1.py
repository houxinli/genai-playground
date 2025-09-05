#!/usr/bin/env python3
"""
Pixiv 小说按作者批量直连下载（路线B）：
- 使用 pixivpy3 通过 refresh-token 登录
- 分页读取指定作者的小说列表（支持 --limit / --offset）
- 每篇输出为单独 .txt 文件（顶部含 YAML front matter，正文为清洗后的日文）
- 文件命名：
    - 有系列信息：{series_id}_{order:03d}_{novel_id}.txt
    - 无系列信息：{novel_id}.txt
- 同目录输出对应 .meta.json；同时维护 {user_id}/index.json（字典结构）与 pixiv/state.json

配置与参数：
- refresh-token 读取优先级：CLI --refresh-token > data/config.json > 环境变量 PIXIV_REFRESH_TOKEN
- 默认测试参数：--limit 3 --offset 0 --workers 2 --rate-limit 1 --retries 5

注意：
- 本脚本不启动任何外部服务；下载速率受 --rate-limit 限制，失败指数退避重试
- ruby 注音统一保留为 "漢字(かな)"；pixiv 特殊语法 [[rb:漢字 > かな]] 也做同样转换
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from pixivpy3 import AppPixivAPI
except Exception as exc:  # pragma: no cover
    raise SystemExit("pixivpy3 未安装，请先运行: pip install --user pixivpy3") from exc

try:
    from bs4 import BeautifulSoup  # type: ignore
except Exception:
    BeautifulSoup = None  # 懒加载依赖，仅在 webview 回退时需要


# -------------------- CLI & Config --------------------


def read_refresh_token_from_config(config_path: Path) -> Optional[str]:
    try:
        if not config_path.exists():
            return None
        data = json.loads(config_path.read_text(encoding="utf-8"))
        token = (
            data.get("extractor", {})
            .get("pixiv", {})
            .get("refresh-token")
        )
        if token:
            return str(token).strip()
    except Exception:
        return None
    return None


def resolve_refresh_token(cli_token: Optional[str], config_path: Path) -> str:
    if cli_token:
        return cli_token.strip()
    token = read_refresh_token_from_config(config_path)
    if token:
        return token
    env = os.getenv("PIXIV_REFRESH_TOKEN", "").strip()
    if env:
        return env
    raise SystemExit("缺少 refresh-token。请通过 --refresh-token、data/config.json 或环境变量 PIXIV_REFRESH_TOKEN 提供。")


def ensure_api(refresh_token: str) -> AppPixivAPI:
    api = AppPixivAPI()
    api.auth(refresh_token=refresh_token)
    return api


# -------------------- Utilities --------------------


def iso_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def sanitize_newlines(text: str) -> str:
    # 统一换行为 \n
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text


def convert_pixiv_rb_syntax(text: str) -> str:
    # 将 [[rb:漢字 > かな]] 转换为 漢字(かな)
    pattern = re.compile(r"\[\[rb:(.+?)\s*>\s*(.+?)\]\]")

    def repl(m: re.Match[str]) -> str:
        kanji = m.group(1).strip()
        kana = m.group(2).strip()
        return f"{kanji}({kana})"

    return pattern.sub(repl, text)


def convert_html_ruby_to_text(html: str) -> str:
    # 解析 <ruby>漢字<rt>かな</rt></ruby> -> 漢字(かな)
    if BeautifulSoup is None:
        return html
    soup = BeautifulSoup(html, "html5lib") if "html5lib" else BeautifulSoup(html, "html.parser")
    for rb in soup.find_all("ruby"):
        rt = rb.find("rt")
        base = rb.get_text("", strip=True)
        kana = rt.get_text("", strip=True) if rt else ""
        replacement = f"{base}({kana})" if kana else base
        rb.replace_with(replacement)
    # 替换 <br> 为换行
    for br in soup.find_all("br"):
        br.replace_with("\n")
    # 简单去除脚本/样式
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text("\n")
    return sanitize_newlines(text)


def build_yaml_frontmatter(meta: Dict[str, Any]) -> str:
    # 仅序列化关键字段，保持与需求一致
    # 注意：简单手写 YAML，避免引入额外依赖
    def yaml_escape(s: Optional[str]) -> str:
        if s is None:
            return ""
        s = str(s)
        s = s.replace("\n", " ")
        return s

    series = meta.get("series") or {}
    author = meta.get("user") or {}
    tags = meta.get("tags") or []

    lines = [
        "---",
        f"novel_id: {meta.get('novel_id')}",
        f"title: {yaml_escape(meta.get('title'))}",
        f"caption: {yaml_escape(meta.get('caption'))}",
        "author:",
        f"  id: {author.get('id')}",
        f"  name: {yaml_escape(author.get('name'))}",
        f"  account: {yaml_escape(author.get('account'))}",
        "series:",
        f"  id: {series.get('id')}",
        f"  title: {yaml_escape(series.get('title'))}",
        f"  order: {series.get('order')}",
        "tags: [" + ", ".join([yaml_escape(t) for t in tags]) + "]",
        f"x_restrict: {meta.get('x_restrict')}",
        f"create_date: {yaml_escape(meta.get('create_date'))}",
        f"update_date: {yaml_escape(meta.get('update_date'))}",
        f"source_url: {yaml_escape(meta.get('url'))}",
        "lang: ja",
        "---",
        "",
    ]
    return "\n".join(lines)


def build_meta(detail: Dict[str, Any]) -> Dict[str, Any]:
    user = detail.get("user") or {}
    series = detail.get("series") or {}
    tags = [t["name"] if isinstance(t, dict) else str(t) for t in (detail.get("tags") or [])]
    novel_id = detail.get("id") or detail.get("novel_id")
    url = f"https://www.pixiv.net/novel/show.php?id={novel_id}" if novel_id else None
    return {
        "novel_id": novel_id,
        "title": detail.get("title"),
        "caption": detail.get("caption"),
        "create_date": detail.get("create_date"),
        "update_date": detail.get("update_date"),
        "x_restrict": detail.get("x_restrict"),
        "word_count": detail.get("text_length"),
        "url": url,
        "user": {
            "id": user.get("id"),
            "name": user.get("name"),
            "account": user.get("account"),
        },
        "series": {
            "id": series.get("id"),
            "title": series.get("title"),
            "order": detail.get("series_nav_data", {}).get("current_order"),
        },
        "tags": tags,
    }


def filename_for(meta: Dict[str, Any]) -> str:
    series = meta.get("series") or {}
    series_id = series.get("id")
    order = series.get("order")
    novel_id = meta.get("novel_id")
    if series_id and isinstance(order, int):
        return f"{series_id}_{order:03d}_{novel_id}.txt"
    return f"{novel_id}.txt"


def rate_limit_sleep(last_ts: List[float], rate_limit_per_sec: float) -> None:
    if rate_limit_per_sec <= 0:
        return
    now = time.time()
    if last_ts:
        elapsed = now - last_ts[0]
        min_interval = 1.0 / rate_limit_per_sec
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
    last_ts[:] = [time.time()]


# -------------------- Core Download Flow --------------------


def iter_user_novels(api: AppPixivAPI, user_id: int) -> Iterable[Dict[str, Any]]:
    # 使用 offset 分页迭代作者小说列表
    offset = 0
    while True:
        res = api.user_novels(user_id, offset=offset)
        novels = (res or {}).get("novels") or []
        for n in novels:
            yield n
        next_url = (res or {}).get("next_url")
        if not next_url:
            break
        qs = api.parse_qs(next_url) or {}
        try:
            offset = int(qs.get("offset", 0))
        except Exception:
            break


def fetch_novel_text_with_fallback(api: AppPixivAPI, novel_id: int, rate_state: List[float], rate_limit: float, retries: int) -> Tuple[str, Dict[str, Any]]:
    # 返回 (cleaned_text, detail_meta)
    backoff = 1.0
    for attempt in range(max(1, retries)):
        try:
            rate_limit_sleep(rate_state, rate_limit)
            detail = api.novel_detail(novel_id)
            novel = (detail or {}).get("novel") or {}
            rate_limit_sleep(rate_state, rate_limit)
            text_res = api.novel_text(novel_id)
            raw_text = (text_res or {}).get("novel_text") or ""
            raw_text = str(raw_text)
            raw_text = sanitize_newlines(raw_text)
            raw_text = convert_pixiv_rb_syntax(raw_text)
            return raw_text, novel
        except Exception:
            # 回退 webview
            try:
                rate_limit_sleep(rate_state, rate_limit)
                web = api.webview_novel(novel_id)
                html = (web or {}).get("novel_text") or (web or {}).get("html") or ""
                html = str(html)
                cleaned = convert_html_ruby_to_text(html)
                # 同时补拉 detail 以构建 meta
                rate_limit_sleep(rate_state, rate_limit)
                detail = api.novel_detail(novel_id)
                novel = (detail or {}).get("novel") or {}
                return cleaned, novel
            except Exception:
                time.sleep(backoff)
                backoff = min(backoff * 2.0, 8.0)
                continue
    raise RuntimeError(f"无法获取小说正文（含回退）: novel_id={novel_id}")


def update_index(index_path: Path, novel_meta: Dict[str, Any], user_id: int) -> None:
    data: Dict[str, Any] = {}
    if index_path.exists():
        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    summary = data.get("_summary") or {
        "user_id": user_id,
        "total_items": 0,
        "last_synced_at": None,
        "latest_update_date": None,
        "by_series": {},
        "version": 1,
    }
    novel_id = str(novel_meta.get("novel_id"))
    data[novel_id] = {
        "novel_id": novel_meta.get("novel_id"),
        "title": novel_meta.get("title"),
        "caption": novel_meta.get("caption"),
        "create_date": novel_meta.get("create_date"),
        "update_date": novel_meta.get("update_date"),
        "x_restrict": novel_meta.get("x_restrict"),
        "word_count": novel_meta.get("word_count"),
        "source_url": novel_meta.get("url"),
        "series": novel_meta.get("series"),
        "tags": novel_meta.get("tags"),
    }
    # 更新 summary
    summary["total_items"] = sum(1 for k in data.keys() if k != "_summary")
    summary["last_synced_at"] = iso_now()
    # latest_update_date
    try:
        cur = novel_meta.get("update_date") or novel_meta.get("create_date")
        latest = summary.get("latest_update_date")
        summary["latest_update_date"] = max(filter(None, [latest, cur]))
    except Exception:
        pass
    # by_series
    s = novel_meta.get("series") or {}
    sid = s.get("id")
    if sid:
        arr = summary["by_series"].get(str(sid)) or []
        if novel_meta.get("novel_id") not in arr:
            arr.append(novel_meta.get("novel_id"))
        try:
            data_series = []
            for nid in arr:
                # 排序依据 order
                # 此处仅按出现顺序保留；如需严格排序可在读取时利用 index.json 的条目进行二次排序
                data_series.append(nid)
            summary["by_series"][str(sid)] = data_series
        except Exception:
            summary["by_series"][str(sid)] = arr
    data["_summary"] = summary
    index_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def update_state(state_path: Path, novel_meta: Dict[str, Any]) -> None:
    state: Dict[str, Any] = {}
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            state = {}
    novel_id = str(novel_meta.get("novel_id"))
    state[novel_id] = {
        "update_date": novel_meta.get("update_date"),
        "create_date": novel_meta.get("create_date"),
    }
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


# -------------------- Main --------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="按作者下载 Pixiv 小说到带 YAML 头的 .txt")
    parser.add_argument("--user-id", type=int, required=True)
    parser.add_argument(
        "--output-root",
        type=Path,
        required=True,
        help="输出根目录，例：tasks/translation/data",
    )
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--rate-limit", type=float, default=1.0, help="每秒请求数上限（近似）")
    parser.add_argument("--retries", type=int, default=5)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--refresh-token", default=None)
    parser.add_argument(
        "--config-json",
        type=Path,
        default=Path("tasks/translation/data/config.json"),
        help="用于读取默认 refresh-token 的配置文件",
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=Path("tasks/translation/logs") / f"batch_download_{datetime.now().strftime('%Y%m%d-%H%M%S')}.log",
    )
    args = parser.parse_args()

    # 解析 token 并登录
    token = resolve_refresh_token(args.refresh_token, args.config_json)
    api = ensure_api(token)

    # 路径约定
    user_dir = args.output_root / "pixiv" / str(args.user_id)
    ensure_dir(user_dir)
    ensure_dir(args.log.parent)

    index_path = user_dir / "index.json"
    state_path = args.output_root / "pixiv" / "state.json"

    # 遍历与限量
    collected: List[int] = []
    rate_state: List[float] = []
    written, skipped, failed = 0, 0, 0

    with args.log.open("a", encoding="utf-8") as logf:
        logf.write(f"[{iso_now()}] START user={args.user_id} limit={args.limit} offset={args.offset} dry_run={args.dry_run}\n")

        for idx, item in enumerate(iter_user_novels(api, args.user_id)):
            if idx < args.offset:
                continue
            if len(collected) >= args.limit:
                break
            novel_id = int(item.get("id") or item.get("novel_id"))
            collected.append(novel_id)

        logf.write(f"[{iso_now()}] to_process={len(collected)} ids={collected}\n")

        for novel_id in collected:
            try:
                text, detail = fetch_novel_text_with_fallback(api, novel_id, rate_state, args.rate_limit, args.retries)
                meta = build_meta(detail)
                yaml_front = build_yaml_frontmatter(meta)
                fname = filename_for(meta)
                txt_path = user_dir / fname
                meta_path = txt_path.with_suffix(".meta.json")

                # 检查是否已存在且包含 YAML 头
                exists_with_header = False
                if txt_path.exists() and not args.overwrite:
                    try:
                        head = txt_path.read_text(encoding="utf-8", errors="ignore").lstrip()
                        exists_with_header = head.startswith("---\n")
                    except Exception:
                        exists_with_header = False
                if exists_with_header and not args.overwrite:
                    skipped += 1
                    logf.write(f"[{iso_now()}] SKIP {txt_path} (exists with header)\n")
                    update_index(index_path, meta, args.user_id)
                    update_state(state_path, meta)
                    continue

                if args.dry_run:
                    logf.write(f"[{iso_now()}] DRYRUN would write {txt_path}\n")
                    update_index(index_path, meta, args.user_id)
                    update_state(state_path, meta)
                    continue

                body = f"{yaml_front}{text}\n"
                txt_path.write_text(body, encoding="utf-8")
                meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
                update_index(index_path, meta, args.user_id)
                update_state(state_path, meta)
                written += 1
                logf.write(f"[{iso_now()}] WRITE {txt_path}\n")
            except Exception as e:
                failed += 1
                logf.write(f"[{iso_now()}] ERROR novel_id={novel_id} {e}\n")

        logf.write(f"[{iso_now()}] DONE written={written} skipped={skipped} failed={failed}\n")

    print(f"done. written={written}, skipped={skipped}, failed={failed}, total={len(collected)}")


if __name__ == "__main__":
    main()


