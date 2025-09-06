#!/usr/bin/env python3
"""
文件处理模块
"""

import glob
import yaml
from pathlib import Path
from typing import List, Tuple, Optional, Dict

from .config import TranslationConfig
from .logger import UnifiedLogger
from .quality_checker import QualityChecker
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
        
        # 2) 若是单 _bilingual 后缀，检查质量
        if name.endswith("_bilingual.txt"):
            if self._check_existing_bilingual_quality(file_path):
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
            bilingual_path = file_path.parent / f"{stem}_bilingual.txt"
            if bilingual_path.exists() and not self.config.overwrite:
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
            error_patterns = ["（以下省略）", "（省略）", "翻译失败", "无法翻译"]
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
        files = []
        
        for input_path in inputs:
            path = Path(input_path)
            
            if path.is_file():
                files.append(path)
            elif path.is_dir():
                # 查找目录中的txt文件
                txt_files = list(path.glob("*.txt"))
                files.extend(txt_files)
            else:
                # 尝试glob模式
                glob_files = glob.glob(input_path)
                files.extend([Path(f) for f in glob_files if Path(f).is_file()])
        
        # 过滤掉不需要处理的文件
        filtered_files = []
        for file_path in files:
            if self._should_process_file(file_path):
                filtered_files.append(file_path)
        
        return filtered_files
