#!/usr/bin/env python3
"""
文件处理模块
"""

import glob
import re
import yaml
from pathlib import Path
from typing import List, Tuple, Optional, Dict

from .config import TranslationConfig
from .logger import UnifiedLogger
from .quality_checker import QualityChecker
from .task import TranslationTask
from ..utils.file import parse_yaml_front_matter


class FileHandler:
    """文件处理类"""
    
    def __init__(self, config: TranslationConfig, logger: UnifiedLogger, quality_checker: QualityChecker):
        """
        初始化文件处理器
        
        Args:
            config: 翻译配置
            logger: 日志器
            quality_checker: 质量检测器
        """
        self.config = config
        self.logger = logger
        self.quality_checker = quality_checker
    
    def _natural_sort_key(self, filename: str) -> List:
        """自然排序键函数，正确处理数字"""
        # 将文件名分割为数字和非数字部分
        parts = re.split(r'(\d+)', filename)
        # 将数字部分转换为整数，非数字部分保持字符串
        return [int(part) if part.isdigit() else part for part in parts]
    
    def _get_file_length(self, file_path: Path) -> int:
        """获取文件长度（字符数）"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return len(content)
        except Exception:
            return 0

    def _looks_like_bilingual_file(self, file_path: Path) -> bool:
        """判断文件是否为双语产物（含 _bilingual/_bilingual_fixed 等）。"""
        markers = ("_bilingual", "_bilingual_fixed", "_awq_bilingual", "_awq_bilingual_fixed")
        name = file_path.name
        if any(marker in name for marker in markers):
            return True
        for ancestor in file_path.parents:
            if any(marker in ancestor.name for marker in ("_bilingual", "_bilingual_fixed")):
                return True
            # 不需要遍历到根目录
            if ancestor.parent == ancestor:
                break
        return False

    def _should_repair_source(self, file_path: Path) -> bool:
        """修复模式下判断文件是否可作为原文输入。"""
        if not file_path.is_file():
            return False
        disallowed_suffixes = (
            "_zh.txt",
            "_awq_zh.txt",
            "_bilingual.txt",
            "_awq_bilingual.txt",
            "_bilingual_fixed.txt",
            "_awq_bilingual_fixed.txt",
        )
        return not any(file_path.name.endswith(suffix) for suffix in disallowed_suffixes)

    def _resolve_existing_bilingual_path(self, original_path: Path) -> Optional[Path]:
        """根据原文推断已有的双语文件路径。"""
        candidates = []
        parent = original_path.parent
        stem = original_path.stem
        base_dir = parent.parent
        base_name = parent.name
        suffixes = [
            "_bilingual",
            "_bilingual_fixed",
            "_awq_bilingual",
            "_awq_bilingual_fixed",
        ]
        for suffix in suffixes:
            candidates.append((base_dir / f"{base_name}{suffix}" / f"{stem}.txt"))
        candidates.append(parent / f"{stem}_bilingual.txt")
        candidates.append(parent / f"{stem}_bilingual_fixed.txt")
        candidates.append(parent / f"{stem}_awq_bilingual.txt")
        candidates.append(parent / f"{stem}_awq_bilingual_fixed.txt")
        for candidate in candidates:
            if candidate and candidate.exists():
                return candidate
        return None

    def _resolve_original_for_bilingual(self, bilingual_path: Path) -> Optional[Path]:
        """根据双语文件推断原文路径。"""
        parent = bilingual_path.parent
        stem = bilingual_path.stem
        candidates = []
        if parent.name.endswith("_bilingual_fixed"):
            base_name = parent.name[: -len("_bilingual_fixed")]
            candidates.append(parent.parent / base_name / f"{stem}.txt")
        if parent.name.endswith("_bilingual"):
            base_name = parent.name[: -len("_bilingual")]
            candidates.append(parent.parent / base_name / f"{stem}.txt")
        if stem.endswith("_bilingual_fixed"):
            candidates.append(parent / f"{stem[: -len('_bilingual_fixed')]}.txt")
        if stem.endswith("_bilingual"):
            candidates.append(parent / f"{stem[: -len('_bilingual')]}.txt")
        if stem.endswith("_awq_bilingual_fixed"):
            candidates.append(parent / f"{stem[: -len('_awq_bilingual_fixed')]}.txt")
        if stem.endswith("_awq_bilingual"):
            candidates.append(parent / f"{stem[: -len('_awq_bilingual')]}.txt")
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def _resolve_repair_output_path(
        self,
        reference_path: Path,
        original_path: Optional[Path] = None,
    ) -> Path:
        """根据参考路径生成修复输出路径。"""
        base = original_path or reference_path
        parent = base.parent
        stem = base.stem
        if parent.name.endswith("_bilingual_fixed"):
            output_dir = parent
        elif parent.name.endswith("_bilingual"):
            output_dir = parent.parent / f"{parent.name}_fixed"
        else:
            output_dir = parent.parent / f"{parent.name}_bilingual_fixed"
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir / f"{stem}.txt"
    
    def process_file(self, file_path: Path) -> bool:
        """
        处理单个文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            是否处理成功
        """
        self.logger.info(f"开始处理文件: {file_path}")
        
        # 文件类型判断与清理
        if not self._should_process_file(file_path):
            return True
        
        # 读取文件内容
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            self.logger.error(f"读取文件失败: {e}")
            return False
        
        # 解析YAML front matter
        yaml_data, text_content = parse_yaml_front_matter(content)
        
        # 显示文章信息
        self._log_article_info(yaml_data, len(text_content))
        
        # 确定输出文件路径
        output_path = self._get_output_path(file_path)
        
        # 检查是否需要处理
        if not self.config.overwrite and output_path.exists():
            self.logger.info(f"输出文件已存在，跳过: {output_path}")
            return True
        
        # 翻译文本
        translated_content = self._translate_content(text_content, yaml_data)
        
        if not translated_content:
            self.logger.error("翻译失败")
            return False
        
        # 保存结果
        return self._save_result(output_path, translated_content, yaml_data)
    
    def _should_process_file(self, file_path: Path) -> bool:
        """判断文件是否需要处理"""
        name = file_path.name
        stem = file_path.stem
        
        # 1) 若是重复的 _bilingual_bilingual.txt，直接删除后返回
        if name.endswith("_bilingual_bilingual.txt"):
            self.logger.info(f"删除重复文件: {file_path}")
            file_path.unlink()
            return False
        
        # 2) 若是单 _bilingual 后缀，检查质量（增强模式跳过此检查）
        if name.endswith("_bilingual.txt"):
            if self.config.enhanced_mode:
                self.logger.info(f"增强模式：处理双语文件: {file_path}")
                return True
            elif self._check_existing_bilingual_quality(file_path):
                self.logger.info(f"现有bilingual文件质量良好，跳过: {file_path}")
                return False
            else:
                self.logger.info(f"现有bilingual文件质量不佳，删除: {file_path}")
                file_path.unlink()
        
        # 3) 若是 _zh 文件，跳过
        if name.endswith("_zh.txt"):
            self.logger.info(f"跳过已翻译文件: {file_path}")
            return False
        
        # 4) 若是无后缀原文，检查是否已有对应的bilingual文件（除非强制覆盖）
        if not any(name.endswith(suffix) for suffix in ["_zh.txt", "_bilingual.txt", "_awq_zh.txt", "_awq_bilingual.txt"]):
            # 检查bilingual-simple模式的输出路径
            if self.config.bilingual_simple:
                # bilingual_simple模式：检查 _bilingual 子目录
                bilingual_dir = file_path.parent.parent / f"{file_path.parent.name}_bilingual"
                bilingual_path = bilingual_dir / f"{stem}.txt"
            else:
                # 普通模式：检查同目录下的bilingual文件
                bilingual_path = file_path.parent / f"{stem}_bilingual.txt"
            
            if bilingual_path.exists() and not self.config.overwrite:
                # Debug模式下，每次都是新文件（带时间戳），不需要跳过
                if self.config.debug:
                    self.logger.info(f"Debug模式：跳过质量检查: {file_path}")
                else:
                    if self._check_existing_bilingual_quality(bilingual_path):
                        self.logger.info(f"已有高质量bilingual文件，跳过: {file_path}")
                        return False
                    else:
                        self.logger.info(f"删除低质量bilingual文件: {bilingual_path}")
                        bilingual_path.unlink()
        
        return True
    
    def _check_existing_bilingual_quality(self, file_path: Path) -> bool:
        """检查现有bilingual文件的质量"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 简单质量检查
            if len(content) < 100:
                return False
            
            # 检查是否包含错误模式
            error_patterns = ["（以下省略）", "（省略）", "无法翻译"]
            for pattern in error_patterns:
                if pattern in content:
                    return False
            
            return True
        except:
            return False
    
    
    def _log_article_info(self, yaml_data: Optional[Dict], text_length: int) -> None:
        """记录文章信息"""
        self.logger.info("📖 文章信息:")
        
        if yaml_data:
            self.logger.info(f"   标题: {yaml_data.get('title', 'N/A')}")
            self.logger.info(f"   作者: {yaml_data.get('author', {}).get('name', 'N/A')}")
            self.logger.info(f"   系列: {yaml_data.get('series', {}).get('title', 'N/A')}")
            self.logger.info(f"   创建时间: {yaml_data.get('create_date', 'N/A')}")
            tags = yaml_data.get('tags', [])
            if tags:
                self.logger.info(f"   标签: {', '.join(tags)}")
        
        self.logger.info(f"   原文长度: {text_length} 字符")
    
    def _get_output_path(self, input_path: Path) -> Path:
        """获取输出文件路径"""
        stem = input_path.stem
        suffix = self.config.get_output_suffix()
        return input_path.parent / f"{stem}{suffix}.txt"
    
    def _translate_content(self, text_content: str, yaml_data: Optional[Dict]) -> str:
        """翻译内容"""
        # 这里应该调用翻译器，暂时返回占位符
        # 实际实现中会调用 Translator 类
        return f"翻译结果: {text_content[:100]}..."
    
    def _save_result(self, output_path: Path, content: str, yaml_data: Optional[Dict]) -> bool:
        """保存翻译结果"""
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            self.logger.info(f"WRITE {output_path}")
            return True
        except Exception as e:
            self.logger.error(f"保存文件失败: {e}")
            return False
    
    def find_files_to_process(self, inputs: List[str]) -> List[Path]:
        """查找需要处理的文件"""
        return [
            task.original_path
            for task in self.plan_tasks(inputs)
            if task.original_path is not None
        ]

    def plan_tasks(self, inputs: List[str]) -> List[TranslationTask]:
        """根据输入路径规划翻译/修复任务。"""
        files: List[Path] = []
        for input_path in inputs:
            path = Path(input_path)
            if path.is_file():
                files.append(path)
            elif path.is_dir():
                txt_files = sorted(path.glob("*.txt"), key=lambda x: self._natural_sort_key(x.name))
                files.extend(txt_files)
            else:
                glob_files = glob.glob(input_path)
                files.extend([Path(f) for f in glob_files if Path(f).is_file()])

        filtered_items: List[Tuple[Path, str]] = []
        for file_path in files:
            if not file_path.is_file():
                continue
            if self._looks_like_bilingual_file(file_path):
                filtered_items.append((file_path, "repair_bilingual"))
                continue
            if self.config.repair_existing:
                if self._should_repair_source(file_path):
                    filtered_items.append((file_path, "repair_original"))
                continue
            if self._should_process_file(file_path):
                filtered_items.append((file_path, "translate"))

        if self.config.sort_by_length:
            filtered_items.sort(key=lambda item: self._get_file_length(item[0]), reverse=True)
            self.logger.info("按文件长度排序（从长到短）")

        tasks: List[TranslationTask] = []
        for file_path, kind in filtered_items:
            if kind == "translate":
                output_path = self._get_output_path(file_path)
                tasks.append(
                    TranslationTask(
                        original_path=file_path,
                        existing_bilingual_path=None,
                        output_path=output_path,
                        mode="translate",
                    )
                )
            elif kind == "repair_original":
                task = self._build_repair_task_from_original(file_path)
                if task:
                    tasks.append(task)
            elif kind == "repair_bilingual":
                task = self._build_repair_task_from_bilingual(file_path)
                if task:
                    tasks.append(task)
        return tasks

    def _build_repair_task_from_original(self, file_path: Path) -> Optional[TranslationTask]:
        existing = self._resolve_existing_bilingual_path(file_path)
        if not existing:
            self.logger.warning(
                f"未找到 {file_path} 对应的双语文件，跳过修复任务。"
            )
            return None
        output_path = self._resolve_repair_output_path(existing, file_path)
        return TranslationTask(
            original_path=file_path,
            existing_bilingual_path=existing,
            output_path=output_path,
            mode="repair",
        )

    def _build_repair_task_from_bilingual(self, file_path: Path) -> Optional[TranslationTask]:
        if not file_path.exists():
            return None
        original = self._resolve_original_for_bilingual(file_path)
        output_path = self._resolve_repair_output_path(file_path, original)
        return TranslationTask(
            original_path=original,
            existing_bilingual_path=file_path,
            output_path=output_path,
            mode="repair",
        )
