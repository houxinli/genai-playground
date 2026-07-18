#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""作者合集:把一个 creator 在各 per-work workspace 里已发布的 rendered 产物,按 source_id 顺序合并成
一本「作者名」命名的整本(zh + bilingual),可选复制到外部目录(如 Google Drive)。

每篇作品翻译时落在自己的 workspace `workspaces/<provider>-<source_id>/`,rendered 在其 `rendered/` 下。
本工具跨 workspace 收集同一 creator 的所有已发布篇(以 `store/refs/<provider>/<creator>/*.json` 为准),
复制 rendered 到一个临时合集目录,再用 `merge_author` 合成 `<author>.zh.txt` / `<author>.bilingual.txt`。
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from .epub_build import build_epub
    from .pipeline_ingest import _chapter_title, _sid_sort_key, merge_author
    from .renderer import add_furigana
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from core.epub_build import build_epub
    from core.pipeline_ingest import _chapter_title, _sid_sort_key, merge_author
    from core.renderer import add_furigana

VARIANTS = ("zh", "bilingual")
# 合集变体全集：zh(纯中文)、bilingual(日中对照)、study(陪读=注解源文+译文，#174)。
# study 从 refs-annotate channel 发布、rendered 为 <sid>.study.txt，且**不加 furigana**(已含注解读音)。
KNOWN_VARIANTS = ("zh", "bilingual", "study")


def _normalize_variants(variants) -> tuple:
    picked = tuple(v for v in KNOWN_VARIANTS if v in set(variants or ()))
    if not picked:
        raise ValueError(f"variants 至少需含 {KNOWN_VARIANTS} 之一")
    return picked

# 日文假名(平/片)——真源文行含假名;中文译文行原则上不含(deepseek 偶有假名残留另算)。
_KANA = re.compile(r"[぀-ゟ゠-ヿ]")


def _annotate_furigana_file(path: Path) -> None:
    """就地给一个**单篇** bilingual 文件的日文源文行加汉字注音(furigana)。

    **按结构判源文,不靠"整行含假名"启发式**——否则中日混排的 tags 行(`源词 / 中文` 同行)
    与含假名残留的中文译文行会被 pykakasi 用日文读音注到中文汉字上(把 `乳交` 注成 `乳(ちち)交(こう)`)。
    规则:①跳过 front-matter(首个 `---` 到次个 `---`,内含中日混排的 title/caption/tags)②body 区
    非空行严格交替 源文/译文,只注源文槽;③再加假名保护:源文槽无假名则跳过(防译文多行导致奇偶漂移
    时误注中文)。pykakasi 缺失时 add_furigana 原样返回。施加在合集副本上,workspace 原件保持原始。"""
    lines = path.read_text(encoding="utf-8").split("\n")
    front_end = -1
    if lines and lines[0].strip() == "---":
        for j in range(1, len(lines)):
            if lines[j].strip() == "---":
                front_end = j
                break
    out: List[str] = lines[: front_end + 1]  # front-matter 原样(front_end=-1 时为空,从头即 body)
    expect_source = True
    for ln in lines[front_end + 1:]:
        if not ln.strip():
            out.append(ln)
            continue
        if expect_source:
            out.append(add_furigana(ln) if _KANA.search(ln) else ln)
        else:
            out.append(ln)
        expect_source = not expect_source
    path.write_text("\n".join(out), encoding="utf-8")


_COLLECTION_SUFFIXES = (".txt", ".epub", ".json")
_MANIFEST_NAME = "collection_manifest.json"


def _guard_out_dir(out_dir: Path, workspaces_root: Path) -> None:
    """rmtree 前置守卫(Codex #143 P1):out_dir 只允许是"专用合集目录"。
    拒绝:与 workspaces_root 相同或为其祖先(会清掉全部 per-work 产物),或已存在但含
    子目录/非合集文件(说明指向了别的东西,如 rendered、per-work workspace、外部同步目录)。
    注:合集目录默认就在 workspaces_root 下(`_collection-<creator>`),位于其内是合法的。"""
    out_r = out_dir.resolve()
    ws_r = workspaces_root.resolve()
    if out_r == ws_r or out_r in ws_r.parents:
        raise ValueError(f"out_dir 不能等于或包含 workspaces_root: {out_dir}")
    if out_dir.exists():
        if not out_dir.is_dir():
            raise ValueError(f"out_dir 已存在且不是目录: {out_dir}")
        for entry in out_dir.iterdir():
            if entry.is_dir() or entry.suffix not in _COLLECTION_SUFFIXES:
                raise ValueError(
                    f"out_dir 已存在且含非合集内容({entry.name}),拒绝清空: {out_dir}")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _published_documents(
    workspaces_root: Path, provider: str, creator_id: str, variants=VARIANTS,
) -> Dict[str, Dict[str, Any]]:
    """已发布 sid → workspace/version；同时兼容 per-work 与 per-creator 布局。

    published 集合与 version_id 以 translate channel 的 `refs/` 为准(作品是否存在的规范来源);
    多 workspace 命中同一 sid 时按 variants 各自 rendered 文件的存在数择优。"""
    refs = sorted(glob.glob(
        str(workspaces_root / "*" / "store" / "refs" / provider / creator_id / "*.json")
    ))
    documents: Dict[str, Dict[str, Any]] = {}
    for ref_name in refs:
        ref_path = Path(ref_name)
        sid = ref_path.stem
        ref = json.loads(ref_path.read_text(encoding="utf-8"))
        version_id = ref.get("version_id")
        if not isinstance(version_id, str) or not version_id:
            raise ValueError(f"current ref 缺 version_id: {ref_path}")
        candidate = {"workspace": ref_path.parents[4], "version_id": version_id}
        previous = documents.get(sid)
        if previous is not None and previous["version_id"] != version_id:
            raise ValueError(
                f"{provider}:{creator_id}:{sid} 在多个 workspace 指向不同版本: "
                f"{previous['version_id']} != {version_id}"
            )
        if previous is None:
            documents[sid] = candidate
            continue
        previous_score = sum(
            (previous["workspace"] / "rendered" / f"{sid}.{variant}.txt").is_file()
            for variant in variants
        )
        candidate_score = sum(
            (candidate["workspace"] / "rendered" / f"{sid}.{variant}.txt").is_file()
            for variant in variants
        )
        if candidate_score > previous_score:
            documents[sid] = candidate
    return dict(sorted(
        documents.items(), key=lambda item: (int(item[0]) if item[0].isdigit() else 0, item[0])
    ))


def _published_sids(workspaces_root: Path, provider: str, creator_id: str) -> Dict[str, Path]:
    """兼容旧调用：返回已发布 sid → workspace 根。"""
    return {
        sid: document["workspace"]
        for sid, document in _published_documents(workspaces_root, provider, creator_id).items()
    }


def verify_collection(
    creator_id: str, *, workspaces_root: Path, out_dir: Path, provider: str = "pixiv"
) -> Dict[str, Any]:
    """核对合集 manifest 与当前 refs、per-document rendered 和整本输出是否仍一致。"""
    workspaces_root = Path(workspaces_root)
    out_dir = Path(out_dir)
    manifest_path = out_dir / _MANIFEST_NAME
    if not manifest_path.is_file():
        return {"ok": False, "documents": 0, "errors": [f"缺合集 manifest: {manifest_path}"]}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "documents": 0, "errors": [f"合集 manifest 无法读取: {exc}"]}
    errors: List[str] = []
    if manifest.get("schema_version") != 1:
        errors.append(f"不支持的 collection manifest schema_version: {manifest.get('schema_version')}")
    if manifest.get("provider") != provider or manifest.get("creator_id") != creator_id:
        errors.append("合集 manifest 的 provider/creator_id 与请求不一致")
    author_name = manifest.get("author_name")
    if not isinstance(author_name, str) or not author_name:
        errors.append("合集 manifest 缺 author_name")
    # 旧 manifest 无 variants 字段 → 默认 zh+bilingual(向后兼容)。
    variants = tuple(v for v in KNOWN_VARIANTS if v in set(manifest.get("variants") or VARIANTS))
    expected_documents = {
        document.get("source_id"): document
        for document in manifest.get("documents", [])
        if isinstance(document, dict) and isinstance(document.get("source_id"), str)
    }
    try:
        current_documents = _published_documents(workspaces_root, provider, creator_id, variants)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"current refs 无法核对: {exc}")
        current_documents = {}
    expected_sids = set(expected_documents)
    current_sids = set(current_documents)
    if expected_sids != current_sids:
        added = sorted(current_sids - expected_sids)
        removed = sorted(expected_sids - current_sids)
        errors.append(f"published refs 已变化: added={added[:10]}, removed={removed[:10]}")
    for sid in sorted(expected_sids & current_sids):
        expected = expected_documents[sid]
        current = current_documents[sid]
        if expected.get("version_id") != current["version_id"]:
            errors.append(
                f"{sid} current version 已变化: {expected.get('version_id')} -> {current['version_id']}"
            )
        expected_hashes = expected.get("rendered_sha256", {})
        for variant in variants:
            source = current["workspace"] / "rendered" / f"{sid}.{variant}.txt"
            if not source.is_file():
                errors.append(f"{sid} 缺 {variant} rendered: {source}")
            elif expected_hashes.get(variant) != _sha256_file(source):
                errors.append(f"{sid}.{variant}.txt 已变化，合集需要重建")
    # 旧 manifest 无 formats 字段 → 默认双格式(向后兼容)。
    manifest_formats = manifest.get("formats") or ["txt", "epub"]
    manifest_formats = [f for f in ("txt", "epub") if f in set(manifest_formats)]
    outputs = manifest.get("outputs", {})
    required_outputs = {
        f"{author_name}_{variant}.{suffix}"
        for variant in variants
        for suffix in manifest_formats
    } if isinstance(author_name, str) and author_name else set()
    if not isinstance(outputs, dict):
        errors.append("合集 manifest.outputs 必须是 object")
        outputs = {}
    elif set(outputs) != required_outputs:
        errors.append(
            f"合集 manifest.outputs 不完整: missing={sorted(required_outputs - set(outputs))}, "
            f"extra={sorted(set(outputs) - required_outputs)}"
        )
    for name, expected_hash in outputs.items():
        output = out_dir / name
        if not output.is_file():
            errors.append(f"合集输出缺失: {output}")
        elif expected_hash != _sha256_file(output):
            errors.append(f"合集输出被修改: {output}")
    expected_count = len(expected_documents)
    # 只核对本合集实际产出的格式对应的章节计数(txt→chapters，epub→epub_chapters)。
    for field, fmt in (("chapters", "txt"), ("epub_chapters", "epub")):
        if fmt not in manifest_formats:
            continue
        counts = manifest.get(field, {})
        for variant in variants:
            if counts.get(variant) != expected_count:
                errors.append(
                    f"manifest {field}.{variant}={counts.get(variant)}，应为 {expected_count}"
                )
    return {"ok": not errors, "documents": expected_count, "errors": errors}


DEFAULT_FORMATS = ("epub",)  # 默认只发 epub(用户 2026-07-16:整本 txt 不再默认发布/同步 GDrive)


def _normalize_formats(formats) -> tuple:
    picked = tuple(f for f in ("txt", "epub") if f in set(formats or ()))
    if not picked:
        raise ValueError("formats 至少需含 'txt' 或 'epub'")
    return picked


def build_collection(
    author_name: str, creator_id: str, *, workspaces_root: Path, out_dir: Path,
    provider: str = "pixiv", gdrive_dir: Optional[Path] = None, furigana: bool = True,
    formats=DEFAULT_FORMATS, variants=VARIANTS,
) -> Dict[str, Any]:
    """收集 creator 已发布篇 → 完整合并成整本；缺任一 variant 时不替换旧合集。

    formats:发布哪些整本格式(('epub',) / ('txt',) / ('txt','epub')),默认只 epub。
    variants:发布哪些变体(zh/bilingual/study 的子集),默认 zh+bilingual;study(陪读)不加 furigana。
    只影响作者级整本产物与 GDrive 同步;逐篇 rendered 不受影响。"""
    if not author_name.strip():
        raise ValueError("author_name 不能为空")
    formats = _normalize_formats(formats)
    variants = _normalize_variants(variants)
    workspaces_root = Path(workspaces_root)
    out_dir = Path(out_dir)
    documents = _published_documents(workspaces_root, provider, creator_id, variants)
    sids = list(documents)
    if not sids:
        raise ValueError(f"{provider}:{creator_id} 没有已发布篇(workspaces 下无 refs)")
    _guard_out_dir(out_dir, workspaces_root)
    missing: List[str] = []
    for sid, document in documents.items():
        ws = document["workspace"]
        for var in variants:
            src = ws / "rendered" / f"{sid}.{var}.txt"
            if not src.is_file():
                missing.append(f"{sid}.{var}")
    if missing:
        raise ValueError(f"{len(missing)} 个已发布 rendered 缺失，拒绝生成部分合集: {missing[:10]}")

    out_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{out_dir.name}-build-", dir=out_dir.parent) as tmp:
        staging = Path(tmp) / "collection"
        staging.mkdir()
        manifest_documents: List[Dict[str, Any]] = []
        for sid, document in documents.items():
            ws = document["workspace"]
            rendered_hashes: Dict[str, str] = {}
            for var in variants:
                src = ws / "rendered" / f"{sid}.{var}.txt"
                rendered_hashes[var] = _sha256_file(src)
                shutil.copy(src, staging / f"{sid}.{var}.txt")
            manifest_documents.append({
                "source_id": sid,
                "version_id": document["version_id"],
                "rendered_sha256": rendered_hashes,
            })
        # furigana 只施于 bilingual;study 已含注解读音,zh 是中文——都不注音。
        if furigana and "bilingual" in variants:
            for sid in sids:
                _annotate_furigana_file(staging / f"{sid}.bilingual.txt")
        merged = merge_author(staging, author_name, sids, variants) if "txt" in formats else {}
        epubs = _build_epubs(staging, author_name, sids, variants) if "epub" in formats else {}
        output_names = [
            f"{author_name}_{var}.{suffix}"
            for var in variants
            for suffix in formats
        ]
        output_hashes = {
            name: _sha256_file(staging / name)
            for name in output_names
            if (staging / name).is_file()
        }
        manifest = {
            "schema_version": 1,
            "provider": provider,
            "creator_id": creator_id,
            "author_name": author_name,
            "formats": list(formats),
            "variants": list(variants),
            "documents": manifest_documents,
            "chapters": {key: value.get("chapters") for key, value in merged.items()},
            "epub_chapters": epubs,
            "outputs": output_hashes,
        }
        (staging / _MANIFEST_NAME).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        verification = verify_collection(
            creator_id, workspaces_root=workspaces_root, out_dir=staging, provider=provider
        )
        if not verification["ok"]:
            raise RuntimeError(f"合集自校验失败: {verification['errors'][:5]}")
        if out_dir.exists():
            shutil.rmtree(out_dir)
        shutil.move(str(staging), str(out_dir))

    files = [str(out_dir / name) for name in output_names]
    gdrive_files: List[str] = []
    if gdrive_dir is not None:
        gdrive_dir = Path(gdrive_dir)
        gdrive_dir.mkdir(parents=True, exist_ok=True)
        for name in output_names:
            # GDrive 上用**人类可读且可区分**的文件名(`<author>·中文.epub` / `<author>·日中对照.epub`):
            # 微信读书等对本地导入 epub 按**文件名**显示、不读 dc:title,统一 `_zh/_bilingual` 会显示成
            # "作者_zh" 或区分不开(用户 2026-07-16)。本地合集目录仍保留 `_var` 规范名不动。
            dst = gdrive_dir / _gdrive_display_name(author_name, name)
            shutil.copy(out_dir / name, dst)
            gdrive_files.append(str(dst))
    return {
        "sids": sids,
        "missing": [],
        "chapters": {k: v.get("chapters") for k, v in merged.items()},
        "epub_chapters": epubs,
        "files": files,
        "manifest": str(out_dir / _MANIFEST_NAME),
        "verification": verification,
        "gdrive": gdrive_files,
    }


# variant → 书名/文件名后缀:让各本 epub 书名不同,阅读器(微信读书等)才能区分。
_VARIANT_TITLE = {"zh": "中文", "bilingual": "日中对照", "study": "陪读"}


def _gdrive_display_name(author_name: str, output_name: str) -> str:
    """本地规范名 `<author>_<var>.<ext>` → GDrive 人类可读名 `<author>·<中文标签>.<ext>`。
    未识别 variant 时原样返回。用于阅读器按文件名显示的场景(微信读书本地导入)。"""
    for var, label in _VARIANT_TITLE.items():
        prefix = f"{author_name}_{var}."
        if output_name.startswith(prefix):
            return f"{author_name}·{label}.{output_name[len(prefix):]}"
    return output_name


def _build_epubs(out_dir: Path, author_name: str, sids: List[str], variants=VARIANTS) -> Dict[str, int]:
    """每个 variant 产 `<author>_<var>.epub`(显式 TOC,阅读器不再从 txt 猜章节)。
    章节与 merge_author 同源:按 source_id 升序,标题取渲染文件的中文 title。
    **书名含 variant**(`<author>·中文` / `<author>·日中对照` / `<author>·陪读`):否则同名、阅读器区分不开。"""
    out: Dict[str, int] = {}
    for var in variants:
        chapters = []
        for sid in sorted(set(sids), key=_sid_sort_key):
            f = out_dir / f"{sid}.{var}.txt"
            if not f.is_file():
                continue
            content = f.read_text(encoding="utf-8").rstrip("\n")
            title = _chapter_title(content) or sid
            chapters.append((f"第{len(chapters) + 1}章 {title}", content))
        if chapters:
            book_title = f"{author_name}·{_VARIANT_TITLE.get(var, var)}"
            build_epub(out_dir / f"{author_name}_{var}.epub", book_title, author_name, chapters)
            out[var] = len(chapters)
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--author", default=None, help="作者名(用作合集文件名,如 錆流浪)")
    p.add_argument("--creator", required=True, help="creator id(如 104039620)")
    p.add_argument("--provider", default="pixiv")
    p.add_argument("--workspaces-root", type=Path, default=Path("tasks/translation/data/workspaces"))
    p.add_argument("--out", type=Path, default=None, help="合集输出目录(默认 workspaces/_collection-<creator>)")
    p.add_argument("--gdrive", type=Path, default=None, help="可选:同时复制整本到此目录")
    p.add_argument("--no-furigana", dest="furigana", action="store_false",
                   help="不给 bilingual 合集的日文源文加汉字注音(默认加)")
    p.add_argument("--verify-only", action="store_true", help="只核对现有合集是否与 current refs/rendered 一致")
    p.add_argument("--formats", default="epub", help="发布哪些整本格式,逗号分隔(epub/txt/txt,epub);默认 epub")
    p.add_argument("--variants", default="zh,bilingual",
                   help="发布哪些变体,逗号分隔(zh/bilingual/study);默认 zh,bilingual。study=陪读(注解版)")
    args = p.parse_args()
    formats = tuple(f.strip() for f in args.formats.split(",") if f.strip())
    variants = tuple(v.strip() for v in args.variants.split(",") if v.strip())
    out = args.out or (args.workspaces_root / f"_collection-{args.creator}")
    if args.verify_only:
        res = verify_collection(args.creator, workspaces_root=args.workspaces_root,
                                out_dir=out, provider=args.provider)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res["ok"] else 1
    if not args.author or not args.author.strip() or not args.creator.strip():
        p.error("构建模式需要非空 --author 与 --creator")
    res = build_collection(args.author, args.creator, workspaces_root=args.workspaces_root,
                           out_dir=out, provider=args.provider, gdrive_dir=args.gdrive,
                           furigana=args.furigana, formats=formats, variants=variants)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
