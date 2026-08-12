#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""篇内实体记忆：首次译名锁定，后续批次只携带 canonical target。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:
    from . import entity_review
    from .entity_store import EntityStore
except ImportError:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from core import entity_review
    from core.entity_store import EntityStore


ENTITY_FINDING_CODE = "entity_first_use"

# 尾随的 E 记录:模型把实体行续在 T 行末尾。实测过的写法(pixiv 9425701 那批):
#   `……绝对。E ペニス 肉棒`  `……乳沟中。[E]ルーナ,露娜`  `……夹住。[E] なし`
# 分隔符可能是空格/TAB/逗号,E 可能被方括号包起来,E 前可能连空格都没有。
# 要求源名含假名才拆——合格译文本就不该有假名,既能认出漏出的 E 记录又不误伤正常中文句尾。
_TRAILING_ENTITY_RE = re.compile(
    r"\[?E\]?[ \t]*([^\s,，]*[ぁ-んァ-ヶ][^\s,，]*)[ \t,，]+([^\s,，]+)\s*$"
)
# `[E] なし`(模型报"本段没有实体")这类只有源名没有译名的残留,同样得从译文里摘掉。
_TRAILING_EMPTY_ENTITY_RE = re.compile(r"\[?E\]?[ \t]+[^\s]*[ぁ-んァ-ヶ][^\s]*\s*$")
# tags 段的 `原词 / 中文` 样式漏进正文段尾(实测 `……好想揉捏……♡）[乳交 / 乳交]`)。
# 要求方括号前有非空白内容 → 整段就是括号列表的 tags 段本身不受影响。
_TRAILING_TAGS_RE = re.compile(r"(?<=\S)\s*\[[^\[\]]+/[^\[\]]+\]\s*$")


def normalize_executor_response(response: str) -> str:
    """把空格塌缩的 T/E 行还原成 TAB 分隔（部分模型如 deepseek 会把 TAB 写成空格）。"""
    lines = response.strip("\r\n").splitlines()
    if not lines:
        return response
    out: List[str] = []
    for index, line in enumerate(lines):
        if line.startswith("T\t") or line.startswith("E\t"):
            out.append(line)
            continue
        if index == 0 and line.startswith("T "):
            out.append("T\t" + line[2:])
            continue
        if line.startswith("E "):
            rest = line[2:]
            if "\t" in rest:
                source, target = rest.split("\t", 1)
                out.append(f"E\t{source.strip()}\t{target.strip()}")
            else:
                parts = rest.split(None, 1)
                if len(parts) == 2:
                    out.append(f"E\t{parts[0]}\t{parts[1]}")
                else:
                    out.append(line)
            continue
        out.append(line)
    return "\n".join(out)


def parse_executor_response(response: str) -> Tuple[str, List[Dict[str, str]]]:
    """解析 API 的简单行协议：首行 ``T<TAB>译文``，随后零到多行 ``E<TAB>源名<TAB>译名``。

    所有响应都必须使用 T/E 协议，避免 API 路线静默跳过篇内名字记忆。
    """
    content = normalize_executor_response(response)
    lines = [line for line in content.splitlines() if line.strip()]
    if not lines or not lines[0].startswith("T\t"):
        raise ValueError("响应首行必须是 `T<TAB>译文`")
    translation = lines[0].split("\t", 1)[1].strip()
    # 译文偶发被模型折行:把紧随 T 行、不以 E 开头的续行并回译文,直到遇到 E 或结束。
    # **但另起一条 T 记录不是"折行"**——那是模型把两段(通常是上文+本段)分别译了。原样并回去会把
    # `T<TAB>…` 原封不动粘进译文(实测 pixiv 27417304 的 34/100/103 段就是这么发布出去的);
    # 这里改成中断合并,让残留的协议行留给下面的 TAB 检查判成协议漂移 → 走调用方的重写重试。
    cursor = 1
    while cursor < len(lines) and not lines[cursor].startswith("E") and not lines[cursor].startswith("T\t"):
        translation = f"{translation}{lines[cursor].strip()}"
        cursor += 1
    observations: List[Dict[str, str]] = []
    # 模型偶发把 E 记录直接续在 T 行末尾且用空格分隔(`……不会改变。E ペニス 肉棒`)。
    # 它确实是想报一个实体,只是分隔符和换行都丢了 → 在解析层拆回来:译文去掉尾巴,观察照收。
    trailing = _TRAILING_ENTITY_RE.search(translation)
    if trailing:
        translation = translation[: trailing.start()].rstrip()
        observations.append({"source": trailing.group(1), "target": trailing.group(2)})
    else:
        empty_entity = _TRAILING_EMPTY_ENTITY_RE.search(translation)
        if empty_entity:
            translation = translation[: empty_entity.start()].rstrip()
    translation = _TRAILING_TAGS_RE.sub("", translation).rstrip()
    if "\t" in translation:
        raise ValueError("译文含 TAB,疑似整条 T/E 协议被塞进了同一物理行")
    for line_number, line in enumerate(lines[cursor:], cursor + 1):
        if line.startswith("T\t"):
            # 第二条 T = 模型把上文和本段各译了一条。此前只是"停止合并"再静默跳过,
            # 结果发布的是**第一条**(上一段的译文)。必须显式拒绝,交给调用方走格式重写。
            raise ValueError("响应含多条 T 记录,无法判断哪条是本段译文")
        if not line.startswith("E"):
            # 协议后的解释/空话忽略,避免小模型偶发尾注拖垮整篇。
            continue
        parts = line.split("\t")
        # 允许多余列(如 E<source><读音><译名>),取首列为源名、末列为译名。
        if len(parts) < 3:
            continue
        source, target = parts[1].strip(), parts[-1].strip()
        if not source or not target:
            continue
        observations.append({"source": source, "target": target})
    return translation, observations


def context_targets(context_pack: Dict[str, Any]) -> Dict[str, str]:
    """取已批准 Context Pack 实体；调用方可在其上追加本文首次译名。"""
    return {entity["source"]: entity["target"] for entity in context_pack.get("entities", [])}


def apply_observations(
    source_text: str,
    translation: str,
    observations: List[Dict[str, str]],
    locked_targets: Dict[str, str],
) -> Tuple[str, List[Dict[str, str]], List[Dict[str, str]]]:
    """按出现顺序合并本段观察；已锁定 target 永不改变，冲突只纠正当前译文。

    ``locked_targets`` 原地追加首次观察。只接受 source 确实在本段源文、target 确实在本段译文中的
    记录，防止模型把提示里的其它名字重新报告进本文记忆。
    """
    first_uses: List[Dict[str, str]] = []
    conflicts: List[Dict[str, str]] = []
    for observation in observations:
        source = observation["source"].strip()
        observed_target = observation["target"].strip()
        if not source or not observed_target or source not in source_text or observed_target not in translation:
            continue
        canonical = locked_targets.get(source)
        if canonical is None:
            locked_targets[source] = observed_target
            first_uses.append({"source": source, "target": observed_target})
            continue
        if observed_target == canonical:
            continue
        if canonical not in translation or observed_target not in canonical:
            translation = translation.replace(observed_target, canonical)
        conflicts.append({"source": source, "target": canonical, "observed_target": observed_target})
    return translation, first_uses, conflicts


def entity_finding(source: str, target: str, segment_id: str, line: int) -> Dict[str, Any]:
    """把本文首次译名装进 Result 既有 findings，避免扩展 Result schema。"""
    evidence = json.dumps(
        {"source": source, "target": target, "segment_id": segment_id},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "code": ENTITY_FINDING_CODE,
        "severity": "info",
        "message": f"本篇首次译名锁定：{source} => {target}",
        "evidence": evidence,
        "line": line,
    }


def entities_from_result(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """从 Result findings 恢复可送 entity-review 的最小提案。"""
    entities: List[Dict[str, Any]] = []
    seen = set()
    for finding in result.get("findings", []):
        if finding.get("code") != ENTITY_FINDING_CODE or not finding.get("evidence"):
            continue
        try:
            evidence = json.loads(finding["evidence"])
        except (TypeError, ValueError):
            continue
        source = str(evidence.get("source", "")).strip()
        target = str(evidence.get("target", "")).strip()
        if not source or not target or source in seen:
            continue
        seen.add(source)
        entities.append({
            "source": source,
            "target": target,
            "type": "person",
            "confidence": 1.0,
            "variants": [],
        })
    return entities


def parse_locked_names_tsv(content: str) -> Dict[str, str]:
    """解析 Agent 的两列篇内锁定表；同 source 出现不同 target 时拒绝。"""
    locked: Dict[str, str] = {}
    for line_number, line in enumerate(content.splitlines(), 1):
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) != 2:
            raise ValueError(f"names.tsv 第 {line_number} 行应为 `日文名<TAB>中文名`")
        source, target = parts[0].strip(), parts[1].strip()
        if not source or not target:
            raise ValueError(f"names.tsv 第 {line_number} 行 source/target 不得为空")
        previous = locked.get(source)
        if previous is not None and previous != target:
            raise ValueError(
                f"names.tsv 第 {line_number} 行违反 first-wins：{source!r} 已锁定为 {previous!r}，"
                f"不得再写 {target!r}"
            )
        locked[source] = target
    return locked


def apply_locked_names(
    bundle: Dict[str, Any],
    translations: Dict[int, str],
    local_targets: Dict[str, str],
) -> Tuple[Dict[int, str], List[Dict[str, Any]]]:
    """Agent finish 时让 approved target 覆盖冲突本地记录，并为真实首次用法生成 findings。"""
    normalized = dict(translations)
    approved = context_targets(bundle.get("context_pack", {}))
    findings: List[Dict[str, Any]] = []
    for source, observed_target in local_targets.items():
        canonical = approved.get(source, observed_target)
        first_index = None
        source_seen = False
        for index, segment in enumerate(bundle["segments"]):
            if source not in segment["source_text"]:
                continue
            source_seen = True
            text = normalized.get(index, "")
            if observed_target not in text:
                continue
            if first_index is None:
                first_index = index
            if observed_target != canonical and observed_target in text:
                if canonical not in text or observed_target not in canonical:
                    normalized[index] = text.replace(observed_target, canonical)
        if source in approved:
            continue
        if not source_seen:
            raise ValueError(f"names.tsv 的 source {source!r} 未出现在本文源文")
        if first_index is None:
            raise ValueError(f"names.tsv 的 target {observed_target!r} 未出现在该 source 对应译文")
        findings.append(entity_finding(
            source,
            canonical,
            bundle["segments"][first_index]["segment_id"],
            first_index + 1,
        ))
    return normalized, findings


def enqueue_entity_reviews(
    revision: Dict[str, Any],
    entities: List[Dict[str, Any]],
    entity_store_root: Path,
    review_queue_root: Path,
) -> List[Dict[str, Any]]:
    """把本篇首次译名交给 entity-review；不自动 approve。"""
    parts = revision["document_id"].split(":")
    if len(parts) != 3:
        raise ValueError(f"document_id 形如 provider:creator:source，实得 {revision['document_id']!r}")
    provider, creator_id, _ = parts
    scope_context = {
        "provider": provider,
        "creator_id": creator_id,
        "document_id": revision["document_id"],
    }
    proposals = []
    for entity in entities:
        segment = next(
            (item for item in revision["segments"] if entity["source"] in item["source_text"]),
            None,
        )
        if segment is None:
            continue
        proposals.append(
            {
                "mention": entity["source"],
                "document_id": revision["document_id"],
                "segment_id": segment["segment_id"],
                "suggested_target": entity["target"],
                "confidence": entity["confidence"],
                "context": segment["source_text"][:80],
                "type": entity["type"],
            }
        )
    return entity_review.import_proposals(
        proposals,
        scope_context,
        EntityStore(entity_store_root),
        entity_review.ReviewQueue(review_queue_root),
    )
