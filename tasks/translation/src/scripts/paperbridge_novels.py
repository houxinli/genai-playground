#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""paperbridge `/novels/` 译文修订页的导出与导入。

导出:把已发布版本(current ref)按篇打成快照 batch,经 SSH 发布到 paperbridge;每段带
document_qa / 假名检查的标记,网页据此筛出值得看的段。只导出已发布的篇——unresolved
的篇没有可修订的版本,不进快照。标题/标签把角色标成未成年人的篇不导出(见 `_MINOR_MARKERS`)。

导入:吃 `novels.cli edits` 取回的逐段修改,**走现有的人工修复路径**:改 `<sid>.zh.tsv`
对应行 → 用 prepare 时的原始 job 重组 result → finish 重新发布(带 parent 血缘推进 ref)。
不另开修复入口(AGENTS.md §8)。三道闸门,任何一道不过整篇跳过并报告,绝不猜:
- 修改的底稿(base_text)必须等于该段当前发布译文——网页上看到的不是现在的版本就不写;
- TSV 必须与发布版本逐段一致——否则重新 finish 会顺带改掉没人动过的段;
- 按当前源 + 实体库重建的 task 必须与原始 job 同 digest——否则 finish 会整份隔离。
发布后逐段核对,被篇内译名锁定等改写掉的修改单独列出。每次写入的修改追加到
`results/<sid>.edits.jsonl` 留档(候选的 producer 沿用原执行器,这份日志是人工改动的唯一记录)。

用法:
    make novels-export CREATOR=9425701 [PROVIDER=pixiv] [IDS=16852374,18137868] [FLAGGED=1] OUT=batch.json
    make novels-import EDITS=edits.json [DRY_RUN=1]
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from ..core import document_qa, entity_harvest, result_assemble, source_identity as si
    from ..core.artifact_store import ArtifactStore
    from ..core.task_export import export_job, resolve_entities_for_revision
    from ..core.translate_user import _sync_result_from_tsv, finish_document
    from .provenance_report import load_published
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from core import document_qa, entity_harvest, result_assemble, source_identity as si
    from core.artifact_store import ArtifactStore
    from core.task_export import export_job, resolve_entities_for_revision
    from core.translate_user import _sync_result_from_tsv, finish_document
    from scripts.provenance_report import load_published

# 与 paperbridge `novels/schemas.py` 的 FlagCode / MAX_SEGMENT_CHARS 保持一致:服务器整批严格校验。
FLAG_CODES = frozenset({
    "kana_residue", "duplicate_translation_distinct_source", "block_paste_run", "neighbor_overlap",
    "undertranslation", "overtranslation", "segment_overlong", "multiline_translation", "context_marker_leak",
})
MAX_SEGMENT_CHARS = 8000
# 平假名/片假名本体;长音符ー和中点・在中文译文里合法,不算残留。
_KANA = re.compile(r"[ぁ-ゖァ-ヺ]")
# 标题/系列名/标签里把角色标成未成年人的作品不导出:这个工具不用于修订涉及未成年人的性内容。
# 没有开关可以绕过。
_MINOR_MARKERS = re.compile(
    r"JS|JC|JK|ＪＫ|ＪＣ|ＪＳ|小学生|中学生|高校生|女子高生|女子中学生|女子小学生|[小中高][◯○〇]生|[◯○〇][KC]"
    r"|ロリ|ロ[◯○〇]|幼女|園児|ショタ")
_META_KINDS = ("metadata.title", "metadata.series_title", "metadata.tags")
# 人名后括注读音「爱花(まなか)」是有意保留的,不算残留。
_READING = re.compile(r"[（(][ぁ-ヿ・ ]+[）)]")


def _creator_name(workspaces_root: Path, creator: str) -> str:
    manifest = workspaces_root / f"_collection-{creator}" / "collection_manifest.json"
    try:
        return json.loads(manifest.read_text(encoding="utf-8")).get("author_name") or creator
    except (OSError, json.JSONDecodeError):
        return creator


def _has_tsv(ws: Path, sid: str) -> bool:
    return (ws / "results" / f"{sid}.zh.tsv").is_file() and (ws / "jobs" / f"{sid}.job.json").is_file()


def resolve_refs(workspaces_root: Path, provider: str, creator: str) -> Tuple[Dict[str, Path], Dict[str, List[str]]]:
    """sid → 选定的 ref。多个 workspace 指向不同版本时不替人选(与合集构建同一口径),记入 conflicts。"""
    by_sid: Dict[str, List[Path]] = collections.defaultdict(list)
    for ref in sorted(workspaces_root.glob(f"*/store/refs/{provider}/{creator}/*.json")):
        by_sid[ref.stem].append(ref)
    chosen: Dict[str, Path] = {}
    conflicts: Dict[str, List[str]] = {}
    for sid, refs in by_sid.items():
        versions = {json.loads(r.read_text(encoding="utf-8"))["version_id"] for r in refs}
        if len(versions) > 1:
            conflicts[sid] = [str(r.parents[4].name) for r in refs]
            continue
        chosen[sid] = next((r for r in refs if _has_tsv(r.parents[4], sid)), refs[0])
    return chosen, conflicts


def segment_flags(revision: Dict[str, Any], texts: Dict[str, str]) -> Dict[str, List[str]]:
    flags: Dict[str, List[str]] = collections.defaultdict(list)
    for finding in document_qa.audit_document_translations(revision["segments"], texts):
        if finding["code"] in FLAG_CODES:
            for seg_id in finding.get("segments", []):
                if finding["code"] not in flags[seg_id]:
                    flags[seg_id].append(finding["code"])
    for seg in revision["segments"]:
        # tags 行按设计写成「原词 / 中文」,带假名是对的。
        if seg["kind"] != "metadata.tags" and _KANA.search(_READING.sub("", texts.get(seg["segment_id"], ""))):
            flags[seg["segment_id"]].append("kana_residue")
    return flags


def build_work(pub: Dict[str, Any], provider: str, creator: str, creator_name: str) -> Dict[str, Any]:
    rev, texts = pub["revision"], pub["texts"]
    flags = segment_flags(rev, texts)
    segments, title, title_zh = [], "", ""
    for seg in rev["segments"]:
        zh = texts.get(seg["segment_id"], "")
        if seg["kind"] == "metadata.title" and not title:
            title, title_zh = seg["source_text"], zh
        segments.append({"n": seg["ordinal"], "kind": seg["kind"], "src": seg["source_text"], "zh": zh,
                         "flags": flags.get(seg["segment_id"], [])})
    counts = pub["producer_counts"]
    top = counts.most_common(1)[0][0] if counts else (None, None, None)
    producer = " · ".join(x for x in (top[1], top[2]) if x)
    return {
        "key": f"{provider}:{creator}:{pub['source_id']}",
        "creator_name": creator_name,
        "title": (title or rev.get("metadata", {}).get("title") or pub["source_id"])[:300],
        "title_zh": title_zh[:300],
        "version_id": pub["version_id"],
        "producer": producer[:120],
        "translated_at": pub["translated_at"] or "",
        "segments": segments,
    }


def export_batch(workspaces_root: Path, provider: str, creator: str, *, ids: Optional[List[str]] = None,
                 flagged_only: bool = False, creator_name: Optional[str] = None) -> Tuple[Dict[str, Any], List[str]]:
    """返回 (batch, 跳过说明)。"""
    refs, conflicts = resolve_refs(workspaces_root, provider, creator)
    notes = [f"{sid}: 多个 workspace 指向不同版本 {wss},先解决再导出" for sid, wss in sorted(conflicts.items())]
    wanted = sorted(refs, key=lambda s: int(s) if s.isdigit() else 0) if ids is None else ids
    name = creator_name or _creator_name(workspaces_root, creator)
    works, minors = [], []
    for sid in wanted:
        if sid not in refs:
            if sid not in conflicts:
                notes.append(f"{sid}: 没有已发布版本(未翻译或 unresolved),不导出")
            continue
        try:
            work = build_work(load_published(refs[sid]), provider, creator, name)
        except (OSError, KeyError, IndexError, json.JSONDecodeError) as exc:
            notes.append(f"{sid}: 读发布版本失败 {type(exc).__name__}: {exc}")
            continue
        if _MINOR_MARKERS.search(" ".join(s["src"] for s in work["segments"] if s["kind"] in _META_KINDS)):
            minors.append(sid)
            continue
        too_long = [s["n"] for s in work["segments"] if max(len(s["src"]), len(s["zh"])) > MAX_SEGMENT_CHARS]
        if too_long:
            notes.append(f"{sid}: 段 {too_long[:5]} 超过 {MAX_SEGMENT_CHARS} 字,服务器会拒收,不导出")
            continue
        if flagged_only and not any(s["flags"] for s in work["segments"]):
            continue
        works.append(work)
    if minors:
        notes.append(f"{len(minors)} 篇的标题/标签把角色标成未成年人,不导出: {', '.join(minors)}")
    batch = {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "works": works}
    return batch, notes


# ---------------------------------------------------------------- import

def _source_path(ws: Path, data_root: Path, provider: str, creator: str, sid: str) -> Optional[Path]:
    candidates = list(ws.glob("src*/*.txt")) + list((data_root / provider / creator).glob("*.txt"))
    for path in candidates:
        if path.stem == sid or path.stem.endswith("_" + sid):
            return path
    return None


def _entity_store_for(job: Dict[str, Any], revision: Dict[str, Any], entity_store: Path) -> Tuple[bool, Optional[Path]]:
    """原始 job 是带实体库还是不带实体库 prepare 的;两者都对不上 → (False, None)。"""
    seg_ids = [s["segment_id"] for s in revision["segments"]]
    if export_job(revision, seg_ids, entities=None)["task_digest"] == job["task_digest"]:
        return True, None
    entities = resolve_entities_for_revision(revision, entity_store)
    if export_job(revision, seg_ids, entities=entities)["task_digest"] == job["task_digest"]:
        return True, entity_store
    return False, None


def _tsv_translations(ws: Path, sid: str, bundle: Dict[str, Any]) -> Dict[int, str]:
    tr = result_assemble.parse_translations_tsv(
        (ws / "results" / f"{sid}.zh.tsv").read_text(encoding="utf-8"), bundle)
    names = ws / "results" / f"{sid}.names.tsv"
    if names.is_file():
        tr, _ = entity_harvest.apply_locked_names(
            bundle, tr, entity_harvest.parse_locked_names_tsv(names.read_text(encoding="utf-8")))
    return tr


def _rewrite_tsv(path: Path, new_texts: Dict[int, str]) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    seen = set()
    for i, line in enumerate(lines):
        cols = line.split("\t")
        if len(cols) >= 2 and cols[0].isdigit() and int(cols[0]) in new_texts:
            cols[-1] = new_texts[int(cols[0])]
            lines[i] = "\t".join(cols)
            seen.add(int(cols[0]))
    missing = set(new_texts) - seen
    if missing:
        raise ValueError(f"TSV 里找不到段 {sorted(missing)[:5]}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def import_work(key: str, edits: List[Dict[str, Any]], *, workspaces_root: Path, data_root: Path,
                entity_store: Path, dry_run: bool) -> Dict[str, Any]:
    provider, creator, sid = key.split(":")
    report: Dict[str, Any] = {"work": key, "edits": len(edits)}
    refs, conflicts = resolve_refs(workspaces_root, provider, creator)
    if sid in conflicts:
        return {**report, "status": "skipped", "reason": f"多个 workspace 指向不同版本 {conflicts[sid]}"}
    if sid not in refs:
        return {**report, "status": "skipped", "reason": "没有已发布版本"}
    ref = refs[sid]
    ws = ref.parents[4]
    if not _has_tsv(ws, sid):
        return {**report, "status": "skipped", "reason": f"{ws.name} 缺 results/{sid}.zh.tsv 或 jobs/{sid}.job.json"}
    pub = load_published(ref)
    rev, published = pub["revision"], pub["texts"]
    bundle = json.loads((ws / "jobs" / f"{sid}.job.json").read_text(encoding="utf-8"))
    seg_by_n = {s["ordinal"]: s for s in rev["segments"]}
    # 网页上的段号 n 是 revision ordinal;TSV 行号是 job 里的段序号。两者必须是同一序列。
    if ([s["segment_id"] for s in bundle["segments"]] != [s["segment_id"] for s in rev["segments"]]
            or [s["ordinal"] for s in rev["segments"]] != list(range(len(rev["segments"])))):
        return {**report, "status": "skipped", "reason": "job 的段与发布版本的 revision 不一致"}

    stale = [e["n"] for e in edits
             if e["n"] not in seg_by_n or published.get(seg_by_n[e["n"]]["segment_id"]) != e["base_text"]]
    if stale:
        return {**report, "status": "skipped",
                "reason": f"段 {stale[:8]} 的发布译文已不是网页上的底稿,先重新导出发布这篇再改"}
    tsv_now = _tsv_translations(ws, sid, bundle)
    drift = [i for i, seg in enumerate(bundle["segments"]) if tsv_now.get(i) != published.get(seg["segment_id"])]
    if drift:
        return {**report, "status": "skipped",
                "reason": f"TSV 与发布版本有 {len(drift)} 段不一致(如段 {drift[:5]}),重新 finish 会改到别的段"}
    src = _source_path(ws, data_root, provider, creator, sid)
    if src is None:
        return {**report, "status": "skipped", "reason": "找不到源文 txt"}
    src_rev = si.build_document_revision(provider, src)
    ok, chosen_entity_store = _entity_store_for(bundle, src_rev, entity_store)
    if src_rev["revision_id"] != rev["revision_id"] or not ok:
        return {**report, "status": "skipped", "reason": "按当前源与实体库重建的 task 与原始 job 不符,finish 会隔离"}

    new_texts = {e["n"]: e["text"] for e in edits}
    if dry_run:
        return {**report, "status": "ready", "workspace": ws.name}

    results = ws / "results"
    tsv_path, result_path = results / f"{sid}.zh.tsv", results / f"{sid}.result.json"
    # finish 没发布时把 TSV/result 还原:否则它们与发布版本漂移,下次导入会被 TSV 闸门拦下。
    backup = {p: p.read_bytes() for p in (tsv_path, result_path) if p.is_file()}
    try:
        _rewrite_tsv(tsv_path, new_texts)
        _sync_result_from_tsv(result_path, tsv_path, ws / "jobs" / f"{sid}.job.json",
                              names_path=results / f"{sid}.names.tsv")
        result = json.loads(result_path.read_text(encoding="utf-8"))
        fin = finish_document(provider, src, ArtifactStore(ws / "store"), result, ws / "rendered",
                              entity_store=chosen_entity_store)
    except Exception:
        for path, content in backup.items():
            path.write_bytes(content)
        raise
    report.update(workspace=ws.name, finish_status=fin.get("status"), version_id=fin.get("version_id"))
    if not fin.get("published"):
        for path, content in backup.items():
            path.write_bytes(content)
        return {**report, "status": "failed", "reason": f"finish 未发布: {fin.get('status')} {fin.get('reasons', '')}"}

    after = load_published(ref)["texts"]
    overridden = [n for n, text in new_texts.items() if after.get(seg_by_n[n]["segment_id"]) != text]
    with (results / f"{sid}.edits.jsonl").open("a", encoding="utf-8") as log:
        for e in edits:
            log.write(json.dumps({**e, "imported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                  "version_id": fin.get("version_id"), "applied": e["n"] not in overridden},
                                 ensure_ascii=False) + "\n")
    report.update(status="republished" if not overridden else "partial", overridden=overridden)
    return report


def import_edits(edits: List[Dict[str, Any]], **kwargs: Any) -> List[Dict[str, Any]]:
    by_work: Dict[str, List[Dict[str, Any]]] = collections.defaultdict(list)
    for edit in edits:
        by_work[edit["work"]].append(edit)
    reports = []
    for key in sorted(by_work):
        try:
            reports.append(import_work(key, sorted(by_work[key], key=lambda e: e["n"]), **kwargs))
        except Exception as exc:  # noqa: BLE001 — 逐篇容错,一篇出错不影响其它篇
            reports.append({"work": key, "status": "failed", "reason": f"{type(exc).__name__}: {exc}"})
    return reports


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    ex = sub.add_parser("export")
    ex.add_argument("--provider", default="pixiv", choices=("pixiv", "fanbox"))
    ex.add_argument("--creator", required=True)
    ex.add_argument("--ids", default="", help="逗号分隔的 source_id;缺省导出该作者全部已发布篇")
    ex.add_argument("--flagged-only", action="store_true", help="只导出至少一段有标记的篇")
    ex.add_argument("--author", default=None, help="网页上显示的作者名;缺省取合集 manifest")
    ex.add_argument("--out", type=Path, required=True)
    im = sub.add_parser("import")
    im.add_argument("--edits", type=Path, required=True, help="novels.cli edits 的输出 JSON")
    im.add_argument("--dry-run", action="store_true")
    im.add_argument("--entity-store", type=Path, default=Path("tasks/translation/data/entities"))
    for p in (ex, im):
        p.add_argument("--workspaces-root", type=Path, default=Path("tasks/translation/data/workspaces"))
    im.add_argument("--data-root", type=Path, default=Path("tasks/translation/data"))
    args = ap.parse_args()

    if args.command == "export":
        ids = [x.strip() for x in args.ids.split(",") if x.strip()] or None
        batch, notes = export_batch(args.workspaces_root, args.provider, args.creator, ids=ids,
                                    flagged_only=args.flagged_only, creator_name=args.author)
        args.out.write_text(json.dumps(batch, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        for note in notes:
            print(f"跳过 {note}", file=sys.stderr)
        flagged = sum(1 for w in batch["works"] for s in w["segments"] if s["flags"])
        print(f"已导出 {args.out}: {len(batch['works'])} 篇,{flagged} 段带标记,"
              f"{args.out.stat().st_size / 1e6:.1f} MB")
        return 0

    payload = json.loads(args.edits.read_text(encoding="utf-8"))
    reports = import_edits(payload.get("edits", payload), workspaces_root=args.workspaces_root,
                           data_root=args.data_root, entity_store=args.entity_store, dry_run=args.dry_run)
    for r in reports:
        extra = r.get("reason") or (f"被改写的段 {r['overridden']}" if r.get("overridden") else "")
        print(f"{r['work']:<28} {r['edits']:>3} 段  {r['status']:<12} {extra}")
    bad = [r for r in reports if r["status"] not in ("republished", "ready")]
    print(f"{'预检' if args.dry_run else '导入'} {len(reports)} 篇,{len(reports) - len(bad)} 篇通过")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
