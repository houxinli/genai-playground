#!/usr/bin/env python3
"""Hard-rule QA gate for translated artifacts."""

from __future__ import annotations

import json
import glob
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

try:
    from ..utils.file import parse_yaml_front_matter
except ImportError:  # unittest discover may import this module as top-level core.qa_gate.
    from utils.file import parse_yaml_front_matter


KANA_RE = re.compile(r"[\u3040-\u309f\u30a0-\u30ff]")
IGNORED_KANA_CHARS = {"・", "ー"}
_QA_GATE_MESSAGES = {
    "empty_translation": "译文行为空",
    "failure_marker": "译文行包含失败标记",
    "refusal_marker": "译文行疑似包含拒绝模板",
    "same_as_source": "译文行与原文完全相同",
    "kana_residue": "译文行残留假名",
}
FAILURE_MARKERS = ("[翻译未完成]", "[翻译失败]", "无法翻译", "（以下省略）", "（省略）")
REFUSAL_MARKERS = (
    "抱歉",
    "不能协助",
    "无法协助",
    "无法提供",
    "不能提供",
    "I can't",
    "I cannot",
    "I'm sorry",
    "I’m sorry",
)


@dataclass(frozen=True)
class QAIssue:
    code: str
    message: str
    severity: str = "error"
    line: Optional[int] = None
    detail: Dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class QAPair:
    source_body_index: int
    source_line: int
    source: str
    translation_body_index: int
    translation_line: int
    translation: str


@dataclass(frozen=True)
class QAReport:
    schema_version: int
    status: str
    source_path: str
    output_path: str
    generated_at: str
    summary: Dict[str, int]
    issues: List[QAIssue]

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == "error" for issue in self.issues)

    def to_dict(self) -> Dict[str, object]:
        data = asdict(self)
        data["has_errors"] = self.has_errors
        return data


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _split_front_matter(lines: List[str]) -> Tuple[List[str], List[str]]:
    if not lines or lines[0].strip() != "---":
        return [], lines
    for idx, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return lines[: idx + 1], lines[idx + 1 :]
    return [], lines


def _contains_kana(text: str) -> bool:
    return any(ch not in IGNORED_KANA_CHARS for ch in KANA_RE.findall(text or ""))


def _is_translatable_source(text: str) -> bool:
    """源是否含可翻译内容(日文假名或汉字)。纯符号/分隔符/拉丁/数字(＊　＊　＊、* * *、---)
    没有可翻译内容,正确译文本就等于原文,不应判 same_as_source。两条硬规则路径共用此判定。"""
    if _contains_kana(text):
        return True
    return any("一" <= ch <= "鿿" for ch in text)  # CJK 汉字


def hard_rule_hits(source: str, translation: str) -> List[Dict[str, str]]:
    """**单一真相源**:对一对 (源, 译) 跑确定性硬规则,返回有序命中 [{code, evidence?}]。

    candidate_eval(新架构)与 TranslationQAGate(离线 gate)都调本函数,避免两份规则各写一遍、改一处漏一处
    (#125)。译文为空时只返回 empty(其余不查)。各调用方把 code 包装成自己的 finding/issue 形态。"""
    if not translation.strip():
        return [{"code": "empty_translation"}]
    hits: List[Dict[str, str]] = []
    for marker in FAILURE_MARKERS:
        if marker in translation:
            hits.append({"code": "failure_marker", "evidence": marker})
    for marker in REFUSAL_MARKERS:
        if marker in translation:
            hits.append({"code": "refusal_marker", "evidence": marker})
    if translation.strip() == source.strip() and _is_translatable_source(source):
        hits.append({"code": "same_as_source"})
    if _contains_kana(translation):
        hits.append({"code": "kana_residue"})
    return hits


def _parse_bilingual_body(body_lines: List[str], line_offset: int = 0) -> Tuple[List[QAPair], List[QAIssue]]:
    pairs: List[QAPair] = []
    issues: List[QAIssue] = []
    idx = 0
    while idx < len(body_lines):
        source = body_lines[idx]
        source_line_no = line_offset + idx + 1
        if not source.strip():
            idx += 1
            continue
        if idx + 1 >= len(body_lines):
            issues.append(
                QAIssue(
                    code="dangling_source_line",
                    message="双语正文存在未配对的原文行",
                    line=source_line_no,
                    detail={"source": source},
                )
            )
            break
        translation = body_lines[idx + 1]
        pairs.append(
            QAPair(
                source_body_index=idx,
                source_line=source_line_no,
                source=source,
                translation_body_index=idx + 1,
                translation_line=line_offset + idx + 2,
                translation=translation,
            )
        )
        idx += 2
    return pairs, issues


def _align_pairs_to_source_body(
    pairs: List[QAPair], source_text: str
) -> Tuple[List[QAPair], List[QAIssue]]:
    """Map bilingual source lines back to source-body indices when the source file is available.

    被跳过或尾部未消费的非空源行说明输出缺失配对(常见于截断),必须报 error 而非静默放过。
    """
    issues: List[QAIssue] = []
    if not source_text:
        return pairs, issues
    source_front, source_body = _split_front_matter(source_text.splitlines())
    if not source_body:
        return pairs, issues
    line_offset = len(source_front)

    def _missing(idx: int) -> QAIssue:
        return QAIssue(
            code="missing_pair",
            message="源文件原文行在输出中没有配对(可能截断或漏行)",
            severity="error",
            line=line_offset + idx + 1,
            detail={"source": source_body[idx].strip()},
        )

    aligned: List[QAPair] = []
    source_idx = 0
    for pair in pairs:
        normalized_source = pair.source.strip()
        matched_idx: Optional[int] = None
        skipped: List[int] = []
        probe = source_idx
        while probe < len(source_body):
            line = source_body[probe].strip()
            if not line:
                probe += 1
                continue
            if line == normalized_source:
                matched_idx = probe
                break
            skipped.append(probe)
            probe += 1
        if matched_idx is None:
            # 输出侧多出的原文行:保留原 pair,不消费源游标,避免后续整体错位
            aligned.append(pair)
            continue
        issues.extend(_missing(idx) for idx in skipped)
        source_idx = matched_idx + 1
        aligned.append(
            QAPair(
                source_body_index=matched_idx,
                source_line=pair.source_line,
                source=pair.source,
                translation_body_index=pair.translation_body_index,
                translation_line=pair.translation_line,
                translation=pair.translation,
            )
        )
    issues.extend(
        _missing(idx) for idx in range(source_idx, len(source_body)) if source_body[idx].strip()
    )
    return aligned, issues


def _load_name_aliases(path: Optional[Path]) -> Dict[str, List[str]]:
    if not path:
        return {}
    aliases: Dict[str, List[str]] = {}
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return aliases
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        jp, rhs = line.split("=", 1)
        jp = jp.strip()
        rhs = rhs.strip()
        if not jp or not rhs:
            continue
        if "|" not in rhs:
            aliases.setdefault(jp, [])
            continue
        canonical, alias_raw = rhs.split("|", 1)
        canonical = canonical.strip()
        values = [item.strip() for item in alias_raw.split(",") if item.strip()]
        aliases[jp] = [value for value in values if value and value != canonical]
    return aliases


def _metadata_issues(source_text: str, output_text: str) -> List[QAIssue]:
    source_yaml, _ = parse_yaml_front_matter(source_text)
    output_yaml, _ = parse_yaml_front_matter(output_text)
    issues: List[QAIssue] = []
    if not source_yaml:
        return issues
    if output_yaml is None:
        issues.append(QAIssue(code="missing_yaml", message="输出缺少 YAML front matter"))
        return issues
    if source_yaml.get("title") and not output_yaml.get("title"):
        issues.append(QAIssue(code="missing_title", message="输出 YAML 缺少 title"))
    source_series = source_yaml.get("series") if isinstance(source_yaml.get("series"), dict) else {}
    output_series = output_yaml.get("series") if isinstance(output_yaml.get("series"), dict) else {}
    if source_series.get("title") and not output_series.get("title"):
        issues.append(QAIssue(code="missing_series_title", message="输出 YAML 缺少 series.title", severity="warning"))
    return issues


class TranslationQAGate:
    """Runs deterministic QA checks over bilingual translation output."""

    def __init__(self, name_rules_file: Optional[Path] = None):
        self.name_rules_file = Path(name_rules_file) if name_rules_file else None
        self.name_aliases = _load_name_aliases(self.name_rules_file)

    @staticmethod
    def _issue_for_pair(
        *,
        pair: QAPair,
        code: str,
        message: str,
        severity: str = "error",
        detail: Optional[Dict[str, object]] = None,
    ) -> QAIssue:
        payload: Dict[str, object] = {
            "source_body_index": pair.source_body_index,
            "translation_body_index": pair.translation_body_index,
            "source_line": pair.source_line,
            "translation_line": pair.translation_line,
        }
        if detail:
            payload.update(detail)
        return QAIssue(code=code, message=message, severity=severity, line=pair.translation_line, detail=payload)

    def run(self, output_path: Path, source_path: Optional[Path] = None) -> QAReport:
        output_path = Path(output_path)
        source_path = Path(source_path) if source_path else None
        output_text = output_path.read_text(encoding="utf-8", errors="ignore")
        source_text = source_path.read_text(encoding="utf-8", errors="ignore") if source_path and source_path.exists() else ""
        output_lines = output_text.splitlines()
        front_matter_lines, body_lines = _split_front_matter(output_lines)
        pairs, issues = _parse_bilingual_body(body_lines, line_offset=len(front_matter_lines))
        pairs, alignment_issues = _align_pairs_to_source_body(pairs, source_text)
        issues.extend(alignment_issues)
        issues.extend(_metadata_issues(source_text, output_text))

        for pair in pairs:
            # 硬规则走单一真相源 hard_rule_hits(与 candidate_eval 同一份);此处只负责包装成 QAIssue。
            for hit in hard_rule_hits(pair.source, pair.translation):
                code = hit["code"]
                evidence = hit.get("evidence")
                message = _QA_GATE_MESSAGES[code] + (f": {evidence}" if evidence else "")
                detail = {"marker": evidence} if evidence else None
                issues.append(self._issue_for_pair(pair=pair, code=code, message=message, detail=detail))
            # 人名坏别名漂移是 qa_gate 专有规则(不在 candidate_eval 硬规则内),空译文跳过。
            translation = pair.translation.strip()
            if translation:
                for jp_name, aliases in self.name_aliases.items():
                    for alias in aliases:
                        if alias in translation:
                            issues.append(
                                self._issue_for_pair(
                                    pair=pair,
                                    code="name_alias_drift",
                                    message=f"译文行命中已知人名坏别名: {alias}",
                                    detail={"jp": jp_name, "alias": alias},
                                )
                            )

        summary = {
            "body_lines": len(body_lines),
            "pairs": len(pairs),
            "issues": len(issues),
            "errors": sum(1 for issue in issues if issue.severity == "error"),
            "warnings": sum(1 for issue in issues if issue.severity == "warning"),
        }
        status = "pass" if summary["errors"] == 0 else "fail"
        return QAReport(
            schema_version=1,
            status=status,
            source_path=str(source_path.resolve(strict=False)) if source_path else "",
            output_path=str(output_path.resolve(strict=False)),
            generated_at=_now(),
            summary=summary,
            issues=issues,
        )

    @staticmethod
    def write_report(report: QAReport, report_path: Path) -> None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def collect_output_files(inputs: Iterable[str]) -> List[Path]:
    files: List[Path] = []
    for raw in inputs:
        path = Path(raw).expanduser()
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(sorted(path.glob("*.txt")))
        else:
            files.extend(Path(match) for match in sorted(glob.glob(raw)) if Path(match).is_file())
    return sorted(set(files))


def infer_source_for_output(output_path: Path) -> Optional[Path]:
    parent = output_path.parent
    stem = output_path.stem
    candidates: List[Path] = []
    suffixes = ("_bilingual_fixed", "_bilingual", "_awq_bilingual_fixed", "_awq_bilingual")
    for suffix in suffixes:
        if parent.name.endswith(suffix):
            base_name = parent.name[: -len(suffix)]
            candidates.append(parent.parent / base_name / f"{stem}.txt")
        if stem.endswith(suffix):
            candidates.append(parent / f"{stem[: -len(suffix)]}.txt")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None
