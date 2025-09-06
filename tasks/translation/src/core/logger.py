#!/usr/bin/env python3
"""
统一日志系统模块
"""

import logging
from datetime import datetime
import sys
from pathlib import Path
from typing import Optional
from enum import Enum, auto


class UnifiedLogger:
    """统一日志系统类"""
    
    def __init__(self, logger: Optional[logging.Logger] = None, log_file_path: Optional[Path] = None, debug_to_console: bool = True):
        """
        初始化统一日志系统
        
        Args:
            logger: Python logging.Logger 对象，如果为None则只输出到控制台
            log_file_path: 日志文件路径
        """
        self.logger = logger
        self.log_file_path = log_file_path
        # 是否将 debug 级别输出到控制台（用于避免与流式输出重复）
        self.debug_to_console = debug_to_console
    
    @classmethod
    def create_console_only(cls) -> 'UnifiedLogger':
        """创建仅控制台输出的日志器"""
        return cls(logger=None)
    
    @classmethod
    def create_for_file(cls, file_path: Path, log_dir: Path, stream_output: bool = True) -> 'UnifiedLogger':
        """
        创建文件和控制台双重输出的日志器
        
        Args:
            file_path: 处理的文件路径
            log_dir: 日志目录
            stream_output: 是否同时输出到控制台
            
        Returns:
            UnifiedLogger 实例
        """
        # 创建日志目录
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成日志文件名
        base_name = Path(file_path).stem
        safe_name = base_name.replace(' ', '_')[:60]  # 控制长度，避免过长
        ts = datetime.now().strftime('%Y%m%d-%H%M%S')
        
        # 在debug模式下，使用与输出文件相同的命名规则
        if hasattr(cls, '_debug_mode') and cls._debug_mode:
            log_file = log_dir / f"{safe_name}_{ts}_bilingual.log"
        else:
            log_file = log_dir / f"translation_{safe_name}_{ts}.log"
        
        # 设置日志器
        logger = logging.getLogger(f'translation_{file_path.stem}')
        logger.setLevel(logging.DEBUG)
        logger.handlers.clear()
        logger.propagate = False
        
        # 文件处理器
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        
        # 控制台处理器（如果启用）
        if stream_output:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logging.INFO)
            console_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
            console_handler.setFormatter(console_formatter)
            logger.addHandler(console_handler)
        
        # 在文件模式下，默认不把 debug 输出到控制台，避免与流式输出重复
        return cls(logger=logger, log_file_path=log_file, debug_to_console=False)

    class LogMode(Enum):
        CONSOLE = auto()
        FILE = auto()
        BOTH = auto()
        NONE = auto()

    def _emit(self, level: str, message: str, mode: Optional['UnifiedLogger.LogMode']) -> None:
        # 默认模式映射
        if mode is None:
            if level == 'DEBUG':
                mode = UnifiedLogger.LogMode.FILE
            else:
                mode = UnifiedLogger.LogMode.BOTH

        to_console = mode in (UnifiedLogger.LogMode.CONSOLE, UnifiedLogger.LogMode.BOTH)
        to_file = mode in (UnifiedLogger.LogMode.FILE, UnifiedLogger.LogMode.BOTH)

        if to_console:
            print(f"[{level}] {message}")
            sys.stdout.flush()
        if to_file and self.logger:
            self.logger.log(getattr(logging, level, logging.INFO), message)
    
    def info(self, message: str, mode: Optional['UnifiedLogger.LogMode'] = None) -> None:
        """输出INFO级别消息"""
        self._emit('INFO', message, mode)
    
    def warning(self, message: str, mode: Optional['UnifiedLogger.LogMode'] = None) -> None:
        """输出WARNING级别消息"""
        self._emit('WARNING', message, mode)
    
    def error(self, message: str, mode: Optional['UnifiedLogger.LogMode'] = None) -> None:
        """输出ERROR级别消息"""
        self._emit('ERROR', message, mode)
    
    def debug(self, message: str, mode: Optional['UnifiedLogger.LogMode'] = None) -> None:
        """输出DEBUG级别消息"""
        # 使用统一发射器，默认仅写文件
        self._emit('DEBUG', message, mode)
    
    def log(self, level: str, message: str, mode: Optional['UnifiedLogger.LogMode'] = None) -> None:
        """输出指定级别消息"""
        self._emit(level.upper(), message, mode)
    
    def get_log_file_path(self) -> Optional[Path]:
        """获取日志文件路径"""
        return self.log_file_path
