#!/usr/bin/env python3
"""翻译流水线的持久化运行状态与输出检查。"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class OutputInspection:
    """输出文件检查结果。"""

    status: str
    reason: str
    source_path: Optional[Path] = None
    output_path: Optional[Path] = None
    manifest_status: str = ""
    placeholder_count: int = 0
    failure_marker_count: int = 0
    content_length: int = 0


class TranslationStateStore:
    """轻量持久化状态存储，记录 run/file 级别的进度。"""

    MANIFEST_FILENAME = "translation_state.json"
    PLACEHOLDER_MARKER = "[翻译未完成]"
    FAILURE_MARKERS = ("[翻译失败]", "无法翻译", "（以下省略）", "（省略）")

    def __init__(self, log_dir: Path):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.log_dir / self.MANIFEST_FILENAME
        self._data = self._load()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    @staticmethod
    def _normalize_path(path: Optional[Path]) -> str:
        if not path:
            return ""
        return str(Path(path).expanduser().resolve(strict=False))

    def _default_data(self) -> Dict[str, Any]:
        return {
            "schema_version": 1,
            "updated_at": self._now(),
            "runs": {},
            "files": {},
        }

    def _load(self) -> Dict[str, Any]:
        if not self.manifest_path.exists():
            return self._default_data()
        try:
            data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return self._default_data()
        except Exception:
            return self._default_data()

        data.setdefault("schema_version", 1)
        data.setdefault("updated_at", self._now())
        data.setdefault("runs", {})
        data.setdefault("files", {})
        return data

    def _write(self) -> None:
        self._data["updated_at"] = self._now()
        payload = json.dumps(self._data, ensure_ascii=False, indent=2, sort_keys=True)
        tmp_path = self.manifest_path.with_suffix(self.manifest_path.suffix + ".tmp")
        tmp_path.write_text(payload, encoding="utf-8")
        os.replace(tmp_path, self.manifest_path)

    def _file_key(self, source_path: Optional[Path], output_path: Path, mode: str) -> str:
        source_key = self._normalize_path(source_path)
        output_key = self._normalize_path(output_path)
        if source_key:
            return f"{mode}:{source_key}->{output_key}"
        return f"{mode}:{output_key}"

    def _get_file_record(
        self,
        source_path: Optional[Path],
        output_path: Path,
        mode: str,
    ) -> Optional[Dict[str, Any]]:
        return self._data.get("files", {}).get(self._file_key(source_path, output_path, mode))

    def _upsert_file_record(
        self,
        *,
        run_id: str = "",
        source_path: Optional[Path],
        output_path: Path,
        mode: str,
        status: str,
        stage: str,
        reason: str = "",
        progress: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        key = self._file_key(source_path, output_path, mode)
        existing = dict(self._data.setdefault("files", {}).get(key, {}))
        existing.update(
            {
                "run_id": run_id or existing.get("run_id", ""),
                "mode": mode,
                "source_path": self._normalize_path(source_path),
                "output_path": self._normalize_path(output_path),
                "status": status,
                "stage": stage,
                "reason": reason,
                "updated_at": self._now(),
            }
        )
        if progress is not None:
            existing["progress"] = progress
        if stage == "start":
            attempts = int(existing.get("attempts", 0) or 0)
            existing["attempts"] = attempts + 1
        self._data["files"][key] = existing
        self._write()
        return existing

    def start_run(
        self,
        *,
        mode: str,
        inputs: list[str],
        target_total: int,
        config_snapshot: Optional[Dict[str, Any]] = None,
    ) -> str:
        run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
        self._data.setdefault("runs", {})[run_id] = {
            "run_id": run_id,
            "mode": mode,
            "inputs": inputs,
            "target_total": target_total,
            "success_count": 0,
            "failure_count": 0,
            "skipped_count": 0,
            "processed_count": 0,
            "status": "running",
            "started_at": self._now(),
            "updated_at": self._now(),
            "finished_at": None,
            "config": config_snapshot or {},
        }
        self._write()
        return run_id

    def update_run_progress(
        self,
        run_id: str,
        *,
        success_delta: int = 0,
        failure_delta: int = 0,
        skipped_delta: int = 0,
        processed_delta: int = 1,
    ) -> None:
        run = self._data.setdefault("runs", {}).get(run_id)
        if not run:
            return
        run["success_count"] = int(run.get("success_count", 0) or 0) + success_delta
        run["failure_count"] = int(run.get("failure_count", 0) or 0) + failure_delta
        run["skipped_count"] = int(run.get("skipped_count", 0) or 0) + skipped_delta
        run["processed_count"] = int(run.get("processed_count", 0) or 0) + processed_delta
        run["updated_at"] = self._now()
        self._write()

    def finish_run(
        self,
        run_id: str,
        *,
        status: str,
        success_count: int,
        failure_count: int,
        skipped_count: int = 0,
    ) -> None:
        run = self._data.setdefault("runs", {}).get(run_id)
        if not run:
            return
        run["status"] = status
        run["success_count"] = success_count
        run["failure_count"] = failure_count
        run["skipped_count"] = skipped_count
        run["finished_at"] = self._now()
        run["updated_at"] = self._now()
        self._write()

    def inspect_output(
        self,
        *,
        source_path: Optional[Path],
        output_path: Path,
        bilingual_simple: bool = False,
    ) -> OutputInspection:
        record = self._get_file_record(source_path, output_path, "translate")
        manifest_status = str(record.get("status", "")) if record else ""

        if not output_path.exists():
            if manifest_status in {"running", "partial", "failed"}:
                return OutputInspection(
                    status=manifest_status,
                    reason=record.get("reason", "manifest indicates unfinished output") if record else "manifest indicates unfinished output",
                    source_path=source_path,
                    output_path=output_path,
                    manifest_status=manifest_status,
                )
            return OutputInspection(
                status="missing",
                reason="输出文件不存在",
                source_path=source_path,
                output_path=output_path,
                manifest_status=manifest_status,
            )

        try:
            content = output_path.read_text(encoding="utf-8")
        except Exception as exc:
            return OutputInspection(
                status="failed",
                reason=f"读取输出文件失败: {exc}",
                source_path=source_path,
                output_path=output_path,
                manifest_status=manifest_status,
            )

        content_length = len(content)
        placeholder_count = content.count(self.PLACEHOLDER_MARKER)
        failure_marker_count = sum(content.count(marker) for marker in self.FAILURE_MARKERS)

        if placeholder_count > 0:
            inspection = OutputInspection(
                status="partial",
                reason=f"发现 {placeholder_count} 处未完成标记",
                source_path=source_path,
                output_path=output_path,
                manifest_status=manifest_status,
                placeholder_count=placeholder_count,
                failure_marker_count=failure_marker_count,
                content_length=content_length,
            )
        elif failure_marker_count > 0:
            inspection = OutputInspection(
                status="failed",
                reason=f"发现 {failure_marker_count} 处失败标记",
                source_path=source_path,
                output_path=output_path,
                manifest_status=manifest_status,
                placeholder_count=placeholder_count,
                failure_marker_count=failure_marker_count,
                content_length=content_length,
            )
        elif content.strip():
            inspection = OutputInspection(
                status="complete",
                reason="输出文件已完成",
                source_path=source_path,
                output_path=output_path,
                manifest_status=manifest_status,
                placeholder_count=placeholder_count,
                failure_marker_count=failure_marker_count,
                content_length=content_length,
            )
        else:
            inspection = OutputInspection(
                status="partial",
                reason="输出文件为空",
                source_path=source_path,
                output_path=output_path,
                manifest_status=manifest_status,
                placeholder_count=placeholder_count,
                failure_marker_count=failure_marker_count,
                content_length=content_length,
            )

        if inspection.status == "complete":
            if not record or manifest_status != "complete":
                self._upsert_file_record(
                    run_id=record.get("run_id", "") if record else "",
                    source_path=source_path,
                    output_path=output_path,
                    mode="translate",
                    status="complete",
                    stage="inspection",
                    reason=inspection.reason,
                    progress={
                        "content_length": content_length,
                        "placeholder_count": placeholder_count,
                        "failure_marker_count": failure_marker_count,
                        "bilingual_simple": bilingual_simple,
                    },
                )
            return inspection

        if inspection.status in {"partial", "failed"}:
            self._upsert_file_record(
                run_id=record.get("run_id", "") if record else "",
                source_path=source_path,
                output_path=output_path,
                mode="translate",
                status=inspection.status,
                stage="inspection",
                reason=inspection.reason,
                progress={
                    "content_length": content_length,
                    "placeholder_count": placeholder_count,
                    "failure_marker_count": failure_marker_count,
                    "bilingual_simple": bilingual_simple,
                },
            )
        return inspection

    def record_file_state(
        self,
        *,
        run_id: str,
        source_path: Optional[Path],
        output_path: Path,
        mode: str,
        status: str,
        stage: str,
        reason: str = "",
        progress: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self._upsert_file_record(
            run_id=run_id,
            source_path=source_path,
            output_path=output_path,
            mode=mode,
            status=status,
            stage=stage,
            reason=reason,
            progress=progress,
        )
