#!/usr/bin/env python3
"""
流式输出处理模块
"""

from typing import Tuple, Dict, Optional
from openai import OpenAI
from .logger import UnifiedLogger
from .config import TranslationConfig


class StreamingHandler:
    """流式输出处理器"""
    
    def __init__(self, client: OpenAI, logger: Optional[UnifiedLogger] = None, config: Optional[TranslationConfig] = None):
        """
        初始化流式输出处理器
        
        Args:
            client: OpenAI客户端
            logger: 日志器
            config: 配置（用于获取行级 flush 阈值）
        """
        self.client = client
        self.logger = logger
        self.config = config
        self._buffer = ""
    
    def stream_completion(self,
                          model: str,
                          messages: list,
                          temperature: float = 0.1,
                          max_tokens: int = 1000,
                          stop: Optional[list] = None,
                          frequency_penalty: float = 0.0,
                          presence_penalty: float = 0.0,
                          repetition_penalty: float = 1.0,
                          no_repeat_ngram_size: int = 0,
                          log_prefix: str = "模型输出") -> Tuple[str, Dict[str, int]]:
        """
        执行流式完成
        
        Args:
            model: 模型名称
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大token数
            stop: 停止词列表
            frequency_penalty: 频率惩罚
            presence_penalty: 存在惩罚
            log_prefix: 日志前缀
            
        Returns:
            (结果文本, token统计信息)
        """
        if self.logger:
            self.logger.info(f"开始{log_prefix}流式调用...")
        
        try:
            req_kwargs = dict(
                model=model,
                messages=messages,
                temperature=temperature,
                frequency_penalty=frequency_penalty,
                presence_penalty=presence_penalty,
                stream=True,
            )
            # 仅当 max_tokens > 0 时才传入；否则由服务端决定
            if isinstance(max_tokens, int) and max_tokens > 0:
                req_kwargs["max_tokens"] = max_tokens
            # 仅当提供 stop 时才传入
            if stop:
                req_kwargs["stop"] = stop
            # 注意：vLLM可能不支持repetition_penalty和no_repeat_ngram_size参数
            # 这些参数主要用于Hugging Face Transformers，在OpenAI API中可能不可用

            resp = self.client.chat.completions.create(**req_kwargs)
            
            result = ""
            current_line = ""
            flush_threshold = getattr(self.config, 'stream_line_flush_chars', 60) if self.config else 60
            # 重复 token 截断控制
            last_piece: Optional[str] = None
            repeat_count: int = 0

            def flush_current_line(reason: str) -> None:
                nonlocal current_line
                if current_line.strip():
                    if self.logger:
                        # 仅写文件
                        self.logger.debug(f"{log_prefix}: {current_line}", mode=UnifiedLogger.LogMode.FILE)
                current_line = ""
            
            for chunk in resp:
                if chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    # 检测重复 token（以增量 piece 作为粒度）
                    piece = content
                    if piece == last_piece:
                        repeat_count += 1
                    else:
                        last_piece = piece
                        repeat_count = 0
                    # 仅当重复的是极短片段（如单字符/空白），并且重复次数很高时才截断
                    if len(piece.strip()) <= 1 and repeat_count > 20:
                        if self.logger:
                            self.logger.warning(f"{log_prefix}: 检测到极短增量内容连续重复超过 20 次，提前截断流。")
                        break
                    result += content
                    current_line += content
                    
                    # 仅将增量内容流式输出到控制台（不通过logger，避免[DEBUG]标签）
                    print(content, end="", flush=True)
                    
                    # 检查是否完成了一行
                    if '\n' in current_line:
                        lines = current_line.split('\n')
                        for line in lines[:-1]:
                            current_line = line
                            flush_current_line('newline')
                        current_line = lines[-1]
                    elif len(current_line) >= flush_threshold:
                        flush_current_line('threshold')
            
            # 收尾：统一用 flush 逻辑
            if current_line:
                flush_current_line('end')
            
            print()  # 换行
            
            # 计算token统计（这里简化处理，实际可能需要更精确的计算）
            token_stats = {
                'input_tokens': len(str(messages)) // 4,  # 粗略估算
                'output_tokens': len(result) // 4,  # 粗略估算
                'total_tokens': 0,
                'max_tokens': max_tokens
            }
            token_stats['total_tokens'] = token_stats['input_tokens'] + token_stats['output_tokens']
            
            return result, token_stats
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"{log_prefix}流式调用失败: {e}")
            raise e
