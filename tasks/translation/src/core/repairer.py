#!/usr/bin/env python3
"""双语修复流程的共享实现。"""

from __future__ import annotations

import re
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .bilingual_writer import BilingualWriter
from .partial_translator import PartialTranslationHelper
from .run_state import TranslationStateStore
from .task import TranslationTask


def parse_body_lines(text: str) -> Tuple[List[str], List[str]]:
    lines = text.splitlines()
    idx = [i for i, line in enumerate(lines) if line.strip() == "---"]
    if len(idx) < 2:
        raise ValueError("输入不包含完整的 YAML front matter")
    return lines[: idx[1] + 1], lines[idx[1] + 1 :]


def load_file_lines(path: Path) -> Tuple[List[str], List[str]]:
    content = path.read_text(encoding="utf-8", errors="ignore")
    return parse_body_lines(content)


def normalize_line(text: str) -> str:
    return text.strip()


def align_existing_translations(
    body_lines: List[str],
    bilingual_body: List[str],
) -> Tuple[List[Optional[str]], List[int]]:
    translations: List[Optional[str]] = [None] * len(body_lines)
    b_idx = 0
    total = len(bilingual_body)
    unmatched: List[int] = []
    for idx, line in enumerate(body_lines):
        if not line.strip():
            continue
        normalized_line = normalize_line(line)
        while b_idx < total and normalize_line(bilingual_body[b_idx]) != normalized_line:
            b_idx += 1
        if b_idx >= total:
            unmatched.append(idx)
            continue
        b_idx += 1
        while b_idx < total and not bilingual_body[b_idx].strip():
            b_idx += 1
        if b_idx < total:
            translations[idx] = bilingual_body[b_idx]
            b_idx += 1
        else:
            unmatched.append(idx)
    return translations, unmatched


def detect_kana_chars(text: str) -> List[str]:
    if not text:
        return []
    chars = {
        ch
        for ch in text
        if "\u3040" <= ch <= "\u30ff" and ch not in {"\u30fb", "\u30fc"}
    }
    return sorted(chars)


def analyze_translation(
    original: str,
    translation: Optional[str],
) -> Tuple[bool, Optional[str], Optional[List[str]]]:
    if translation is None:
        return True, "missing", None
    stripped = translation.strip()
    if not stripped:
        return True, "empty", None
    if stripped in {"[翻译未完成]", "[翻译失败]"}:
        return True, "placeholder", None
    if stripped == original.strip():
        return True, "same_as_original", None
    kana_chars = detect_kana_chars(stripped)
    if kana_chars:
        return True, "kana", kana_chars
    return False, None, None


def has_japanese(text: str) -> bool:
    if not text:
        return False
    normalized = text.replace("\u30fb", "").replace("\u30fc", "")
    if not normalized.strip():
        return False
    return bool(re.search(r"[\u3040-\u309f\u30a0-\u30ff]", normalized))


def build_segments(body_lines: List[str], missing_mask: List[bool]) -> List[Tuple[int, int]]:
    segments = []
    i = 0
    n = len(body_lines)
    while i < n:
        if not missing_mask[i]:
            i += 1
            continue
        start = i
        end = i
        i += 1
        while i < n:
            if missing_mask[i]:
                end = i
                i += 1
            elif not body_lines[i].strip():
                end = i
                i += 1
            else:
                break
        segments.append((start, end))
    return segments


def format_line_spans(numbers: List[int]) -> str:
    if not numbers:
        return ""
    numbers = sorted(numbers)
    spans: List[str] = []
    start = prev = numbers[0]
    for num in numbers[1:]:
        if num == prev + 1:
            prev = num
            continue
        spans.append(str(start) if start == prev else f"{start}-{prev}")
        start = prev = num
    spans.append(str(start) if start == prev else f"{start}-{prev}")
    return ", ".join(spans)


REPAIRABLE_QA_CODES = {
    "empty_translation",
    "failure_marker",
    "refusal_marker",
    "same_as_source",
    "kana_residue",
    "name_alias_drift",
}


def load_repair_indices_from_qa_report(report_path: Optional[Path]) -> Dict[int, List[str]]:
    """Load source-body line indices from a QA report for targeted repair."""
    if not report_path:
        return {}
    path = Path(report_path)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    collected: Dict[int, set[str]] = {}
    for issue in data.get("issues", []):
        if issue.get("severity", "error") != "error":
            continue
        code = str(issue.get("code", ""))
        if code not in REPAIRABLE_QA_CODES:
            continue
        detail = issue.get("detail", {})
        if not isinstance(detail, dict) or "source_body_index" not in detail:
            continue
        try:
            idx = int(detail["source_body_index"])
        except (TypeError, ValueError):
            continue
        collected.setdefault(idx, set()).add(code)
    return {idx: sorted(codes) for idx, codes in collected.items()}


@dataclass(frozen=True)
class RepairResult:
    success: bool
    status: str
    reason: str
    repaired_lines: int = 0
    unresolved_lines: Tuple[int, ...] = ()


class BilingualRepairer:
    """共享的 bilingual 修复器。"""

    def __init__(
        self,
        config,
        translator,
        logger,
        state_store: Optional[TranslationStateStore] = None,
    ):
        self.config = config
        self.translator = translator
        self.logger = logger
        self.state_store = state_store
        self.helper = PartialTranslationHelper(config, translator)

    def _record_state(
        self,
        *,
        run_id: str,
        task: TranslationTask,
        status: str,
        stage: str,
        reason: str,
        progress: Optional[Dict[str, object]] = None,
    ) -> None:
        if not self.state_store:
            return
        source_path = task.original_path or task.existing_bilingual_path
        self.state_store.record_file_state(
            run_id=run_id,
            source_path=source_path,
            output_path=task.output_path,
            mode="repair",
            status=status,
            stage=stage,
            reason=reason,
            progress=progress,
        )

    @staticmethod
    def _extract_original_from_bilingual(existing_body: List[str]) -> List[str]:
        extracted_originals: List[str] = []
        i = 0
        while i < len(existing_body):
            extracted_originals.append(existing_body[i])
            if existing_body[i].strip():
                i += 2
            else:
                i += 1
        return extracted_originals

    @staticmethod
    def _limit_segments(
        segments: List[Tuple[int, int]],
        missing_mask: List[bool],
        max_lines: int,
    ) -> List[Tuple[int, int]]:
        if max_lines <= 0:
            return segments
        total_needed = sum(1 for flag in missing_mask if flag)
        if total_needed <= max_lines:
            return segments

        allowed = max_lines
        limited_segments: List[Tuple[int, int]] = []
        for start, end in segments:
            needed_in_segment = sum(1 for idx in range(start, end + 1) if missing_mask[idx])
            if needed_in_segment <= allowed:
                limited_segments.append((start, end))
                allowed -= needed_in_segment
                continue
            count = 0
            new_end = end
            for idx in range(start, end + 1):
                if missing_mask[idx]:
                    count += 1
                if count > allowed:
                    new_end = idx - 1
                    break
            limited_segments.append((start, new_end))
            break
        return limited_segments

    def repair_task(
        self,
        task: TranslationTask,
        *,
        run_id: str = "",
        max_lines: int = 0,
        qa_report_path: Optional[Path] = None,
    ) -> RepairResult:
        existing_path = task.existing_bilingual_path
        if not existing_path:
            reason = "缺少待修复的双语文件路径"
            self.logger.error(reason)
            self._record_state(
                run_id=run_id,
                task=task,
                status="failed",
                stage="start",
                reason=reason,
            )
            return RepairResult(success=False, status="failed", reason=reason)

        self._record_state(
            run_id=run_id,
            task=task,
            status="running",
            stage="start",
            reason="开始修复双语文件",
        )

        try:
            target = task.original_path or existing_path
            self.translator.current_output_path = str(task.output_path)
            self.logger.info(f"🛠 修复目标: {target}")
            self.logger.info(f"📄 输出文件: {task.output_path}")

            original_yaml: List[str] = []
            original_body: List[str] = []
            if task.original_path and task.original_path.exists():
                original_yaml, original_body = load_file_lines(task.original_path)

            existing_yaml, existing_body = parse_body_lines(
                existing_path.read_text(encoding="utf-8", errors="ignore")
            )
            if not original_body:
                original_body = self._extract_original_from_bilingual(existing_body)
                original_yaml = existing_yaml

            base_yaml = existing_yaml if existing_yaml else original_yaml
            existing_trans, unmatched = align_existing_translations(original_body, existing_body)
            qa_repair_indices = load_repair_indices_from_qa_report(qa_report_path)
            if qa_repair_indices:
                self.logger.info(f"从 QA 报告导入 {len(qa_repair_indices)} 行待修复: {qa_report_path}")
            if unmatched:
                snippets = ", ".join(
                    f"{idx + 1}: {original_body[idx][:20].strip()}" for idx in unmatched[:5]
                )
                extra = "..." if len(unmatched) > 5 else ""
                self.logger.warning(f"未在旧双语中对齐的原文行（仅列前5条）: {snippets}{extra}")

            missing_mask: List[bool] = []
            issues: Dict[int, Tuple[str, Optional[List[str]]]] = {}
            for idx_line, (orig_line, trans_line) in enumerate(zip(original_body, existing_trans)):
                if not orig_line.strip():
                    missing_mask.append(False)
                    continue
                needs, reason, details = analyze_translation(orig_line, trans_line)
                if idx_line in qa_repair_indices:
                    needs = True
                    reason = "qa_report"
                    details = qa_repair_indices[idx_line]
                missing_mask.append(needs)
                if needs and reason:
                    issues[idx_line] = (reason, details)

            for idx_line, (orig_line, is_missing) in enumerate(zip(original_body, missing_mask)):
                if not is_missing:
                    continue
                if idx_line in qa_repair_indices:
                    continue
                if has_japanese(orig_line):
                    continue
                existing_trans[idx_line] = orig_line
                missing_mask[idx_line] = False
                issues.pop(idx_line, None)

            for idx_line in sorted(issues.keys()):
                reason, details = issues[idx_line]
                if reason == "kana" and details:
                    self.logger.info(f"行 {idx_line + 1} 含假名 -> {'/'.join(details)}")
                elif reason == "placeholder":
                    self.logger.info(f"行 {idx_line + 1} 仍为占位符")
                elif reason == "empty":
                    self.logger.info(f"行 {idx_line + 1} 译文为空")
                elif reason == "same_as_original":
                    self.logger.info(f"行 {idx_line + 1} 与原文完全相同")
                elif reason == "qa_report" and details:
                    self.logger.info(f"行 {idx_line + 1} 由 QA 报告要求修复 -> {'/'.join(details)}")
                else:
                    self.logger.info(f"行 {idx_line + 1} 判定缺失: {reason}")

            segments = build_segments(original_body, missing_mask)
            segments = self._limit_segments(segments, missing_mask, max_lines)

            total_missing = sum(1 for flag in missing_mask if flag)
            planned_missing = sum(
                1
                for start, end in segments
                for idx in range(start, end + 1)
                if missing_mask[idx]
            )

            writer = BilingualWriter(base_yaml, original_body, existing_trans[:], task.output_path)
            if not segments:
                writer.finalize()
                reason = "没有检测到需要修复的行，已保留现有双语文件"
                self.logger.info(reason)
                self._record_state(
                    run_id=run_id,
                    task=task,
                    status="complete",
                    stage="save",
                    reason=reason,
                    progress={
                        "repaired_lines": 0,
                        "planned_missing": 0,
                        "total_missing": total_missing,
                    },
                )
                return RepairResult(success=True, status="complete", reason=reason)

            self.logger.info(f"将翻译缺失行 {planned_missing}/{total_missing} 行")
            updated_indices: List[int] = []

            def _on_segment_complete(updates: Dict[int, str]) -> None:
                writer.update(updates, flush=True)
                updated_indices.extend(idx + 1 for idx in updates.keys())
                self._record_state(
                    run_id=run_id,
                    task=task,
                    status="partial",
                    stage="segment",
                    reason="修复片段已写入",
                    progress={
                        "repaired_lines": len(sorted(set(updated_indices))),
                        "planned_missing": planned_missing,
                        "total_missing": total_missing,
                    },
                )

            new_translations = self.helper.translate_segments(
                original_body,
                segments,
                reference_translations=writer.translations,
                on_segment_complete=_on_segment_complete,
            )

            for idx_line, value in new_translations.items():
                writer.translations[idx_line] = value
            writer.finalize()

            unresolved = []
            for idx_line, orig_line in enumerate(original_body):
                if not orig_line.strip():
                    continue
                needs, _, _ = analyze_translation(orig_line, writer.translations[idx_line])
                if needs:
                    unresolved.append(idx_line + 1)

            if updated_indices:
                unique = sorted(set(updated_indices))
                self.logger.info(f"本次修复 {len(unique)} 行: {format_line_spans(unique)}")
            if unresolved:
                reason = f"仍有 {len(unresolved)} 行需人工处理: {format_line_spans(unresolved)}"
                self.logger.warning(reason)
                self._record_state(
                    run_id=run_id,
                    task=task,
                    status="partial",
                    stage="save",
                    reason=reason,
                    progress={
                        "repaired_lines": len(sorted(set(updated_indices))),
                        "planned_missing": planned_missing,
                        "total_missing": total_missing,
                        "unresolved_lines": unresolved,
                    },
                )
                return RepairResult(
                    success=False,
                    status="partial",
                    reason=reason,
                    repaired_lines=len(sorted(set(updated_indices))),
                    unresolved_lines=tuple(unresolved),
                )

            reason = "修复完成"
            self._record_state(
                run_id=run_id,
                task=task,
                status="complete",
                stage="save",
                reason=reason,
                progress={
                    "repaired_lines": len(sorted(set(updated_indices))),
                    "planned_missing": planned_missing,
                    "total_missing": total_missing,
                },
            )
            return RepairResult(
                success=True,
                status="complete",
                reason=reason,
                repaired_lines=len(sorted(set(updated_indices))),
            )
        except Exception as exc:
            reason = f"修复失败: {exc}"
            self.logger.error(reason)
            self._record_state(
                run_id=run_id,
                task=task,
                status="failed",
                stage="exception",
                reason=reason,
            )
            return RepairResult(success=False, status="failed", reason=reason)
