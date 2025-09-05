#!/usr/bin/env python3
"""
翻译流程控制模块
"""

import time
from pathlib import Path
from typing import List, Tuple, Dict, Optional

from .config import TranslationConfig
from .logger import UnifiedLogger
from .quality_checker import QualityChecker
from .translator import Translator
from .file_handler import FileHandler


class TranslationPipeline:
    """翻译流程控制类"""
    
    def __init__(self, config: TranslationConfig):
        """
        初始化翻译流程
        
        Args:
            config: 翻译配置
        """
        self.config = config
        
        # 初始化组件
        self.logger = UnifiedLogger.create_console_only()
        self.quality_checker = QualityChecker(config, self.logger)
        self.translator = Translator(config, self.logger, self.quality_checker)
        self.file_handler = FileHandler(config, self.logger, self.quality_checker)
    
    def run(self, inputs: List[str]) -> int:
        """
        运行翻译流程
        
        Args:
            inputs: 输入文件/目录列表
            
        Returns:
            成功处理的文件数量
        """
        # 验证配置
        errors = self.config.validate()
        if errors:
            for error in errors:
                self.logger.error(f"配置错误: {error}")
            return 0
        
        # 查找文件
        files_to_process = self.file_handler.find_files_to_process(inputs)
        
        if not files_to_process:
            self.logger.warning("没有找到需要处理的文件")
            return 0
        
        self.logger.info(f"开始处理 {len(files_to_process)} 个文件")
        
        # 应用限制
        if self.config.limit > 0:
            files_to_process = files_to_process[:self.config.limit]
            self.logger.info(f"限制处理文件数量为: {len(files_to_process)}")
        
        # 处理文件
        success_count = 0
        for i, file_path in enumerate(files_to_process, 1):
            self.logger.info(f"处理文件 {i}/{len(files_to_process)}: {file_path}")
            
            # 在显式调试模式下限制重试次数以加快迭代
            if getattr(self.config, 'debug', False):
                if self.config.retries > 1:
                    self.logger.info("调试模式下将重试次数限制为 1")
                    self.config.retries = 1

            if self.process_file(file_path):
                success_count += 1
            else:
                self.logger.error(f"文件处理失败: {file_path}")
        
        self.logger.info(f"处理完成: {success_count}/{len(files_to_process)} 个文件成功")
        return success_count
    
    def process_file(self, path: Path) -> bool:
        """
        处理单个文件
        
        Args:
            path: 文件路径
        
        Returns:
            是否处理成功
        """
        # 设置日志
        log_file_path = None
        if self.config.realtime_log:
            # 文件日志 + 控制台输出由自定义 _emit 打印，避免 handler 再次打印导致重复
            self.logger = UnifiedLogger.create_for_file(path, self.config.log_dir, stream_output=False)
            self.translator.logger = self.logger
            self.file_handler.logger = self.logger
            # 同步更新质量检测与流式处理器上的logger，避免控制台重复调试输出
            if hasattr(self.quality_checker, 'logger'):
                self.quality_checker.logger = self.logger
            if hasattr(self.translator, 'streaming_handler') and self.translator.streaming_handler:
                self.translator.streaming_handler.logger = self.logger
            if hasattr(self.quality_checker, 'streaming_handler') and self.quality_checker.streaming_handler:
                self.quality_checker.streaming_handler.logger = self.logger
            # 获取日志文件路径
            log_file_path = self.logger.get_log_file_path()
            self.logger.info(f"开始处理文件: {path}")
            self.logger.info(f"📝 日志文件路径: {log_file_path}")
        else:
            self.logger.info(f"开始处理文件: {path}")
        
        # 显示配置信息
        self._log_config_info()
        
        # 读取文件内容
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            self.logger.error(f"读取文件失败: {e}")
            return False
        
        # 解析YAML front matter
        yaml_data, text_content = self._parse_yaml_front_matter(content)
        
        # 显示文章信息
        self._log_article_info(yaml_data, len(text_content))
        
        # 确定输出文件路径
        output_path = self._get_output_path(path)
        
        # 检查是否需要处理
        if not self.config.overwrite and output_path.exists():
            self.logger.info(f"输出文件已存在，跳过: {output_path}")
            return True
        
        # 翻译文本
        translated_content = self._translate_text(text_content)
        
        if not translated_content:
            self.logger.error("翻译失败")
            return False
        
        # 保存结果
        return self._save_result(output_path, translated_content, yaml_data)
    
    def _log_config_info(self) -> None:
        """记录配置信息"""
        self.logger.info("🔧 翻译配置:")
        self.logger.info(f"   模型: {self.config.model}")
        self.logger.info(f"   模式: {self.config.mode}")
        self.logger.info(f"   对照模式: {self.config.bilingual}")
        self.logger.info(f"   流式输出: {self.config.stream}")
        self.logger.info(f"   实时日志: {self.config.realtime_log}")
        self.logger.info(f"   块大小: {self.config.chunk_size_chars} 字符")
        self.logger.info(f"   重叠大小: {self.config.overlap_chars} 字符")
        self.logger.info(f"   重试次数: {self.config.retries}")
        self.logger.info(f"   重试等待: {self.config.retry_wait} 秒")
        self.logger.info(f"   上下文长度: {self.config.get_max_context_length()}")
        self.logger.info(f"   温度: {self.config.temperature}")
        self.logger.info(f"   频率惩罚: {self.config.frequency_penalty}")
        self.logger.info(f"   存在惩罚: {self.config.presence_penalty}")
        self.logger.info(f"   术语文件: {self.config.terminology_file}")
        self.logger.info(f"   示例文件: {self.config.sample_file}")
        self.logger.info(f"   前言文件: {self.config.preface_file}")
        self.logger.info(f"   停止词: {self.config.stop}")
        self.logger.info(f"   日志目录: {self.config.log_dir}")
        self.logger.info("   ==================================================")
    
    def _parse_yaml_front_matter(self, content: str) -> Tuple[Optional[Dict], str]:
        """解析YAML front matter"""
        if not content.startswith('---'):
            return None, content
        
        try:
            import yaml
            parts = content.split('---', 2)
            if len(parts) < 3:
                return None, content
            
            yaml_content = parts[1].strip()
            text_content = parts[2].strip()
            
            yaml_data = yaml.safe_load(yaml_content)
            return yaml_data, text_content
        except:
            return None, content
    
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
    
    def _translate_text(self, text_content: str) -> str:
        """翻译文本内容"""
        max_ctx = self.config.get_max_context_length()
        estimated_input_tokens = len(text_content) // 2
        margin = 2000
        # 在双语模式下更积极地分块，避免输出被截断
        bilingual_long = self.config.bilingual and len(text_content) > 8000
        need_chunk = (
            self.config.mode == "chunked"
            or estimated_input_tokens > (max_ctx - margin)
            or len(text_content) > self.config.chunk_size_chars
            or bilingual_long
        ) or (self.config.bilingual and len(text_content) > 6000)

        if need_chunk:
            self.logger.info("输入较长，启用分块翻译…")
            # 为保证双语充足输出，进一步缩小单块长度，避免上下文溢出与输出截断
            if self.config.bilingual:
                chunk_size = 3000
                overlap = max(0, min(self.config.overlap_chars, 400)) or 400
            else:
                chunk_size = min(self.config.chunk_size_chars, 8000)
                overlap = max(0, self.config.overlap_chars)
            chunks = []
            start = 0
            n = len(text_content)
            while start < n:
                end = min(n, start + chunk_size)
                chunk = text_content[start:end]
                chunks.append(chunk)
                if end >= n:
                    break
                start = end - overlap if overlap > 0 else end

            results: list[str] = []
            for idx, chunk in enumerate(chunks, 1):
                self.logger.info(f"翻译分块 {idx}/{len(chunks)}，长度: {len(chunk)}")
                result, prompt, success, token_meta = self.translator.translate_text(chunk, chunk_index=idx)
                if not success or not result:
                    self.logger.warning(f"分块 {idx} 翻译失败，返回空字符串以继续拼接")
                    result = ""
                else:
                    self.logger.info(f"Token使用情况: {token_meta}")
                results.append(result)
            return "\n".join(results)

        # 不需要分块，直接单块翻译
        result, prompt, success, token_meta = self.translator.translate_text(text_content)
        if not success:
            self.logger.error("翻译失败")
            return ""
        self.logger.info(f"Token使用情况: {token_meta}")
        return result
    
    def _save_result(self, output_path: Path, content: str, yaml_data: Optional[Dict]) -> bool:
        """保存翻译结果"""
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            self.logger.info(f"WRITE {output_path}")
            
            # 记录日志文件路径（如果启用了实时日志）
            if self.config.realtime_log and hasattr(self.logger, 'get_log_file_path'):
                log_file_path = self.logger.get_log_file_path()
                if log_file_path:
                    self.logger.info(f"📝 日志文件路径: {log_file_path}")
            
            return True
        except Exception as e:
            self.logger.error(f"保存文件失败: {e}")
            return False
