#!/usr/bin/env python3
"""
流式输出处理模块
"""

from typing import Tuple, Dict, Optional, List
from dataclasses import dataclass
import time
from openai import OpenAI
from openai import BadRequestError
from .logger import UnifiedLogger
from .config import TranslationConfig
from .profile_manager import ProfileManager, GenerationParams


class StreamingHandler:
    """流式输出处理器"""
    
    def __init__(self, client: OpenAI, logger: Optional[UnifiedLogger] = None, config: Optional[TranslationConfig] = None, profile_manager: Optional[ProfileManager] = None):
        """
        初始化流式输出处理器
        
        Args:
            client: OpenAI客户端
            logger: 日志器
            config: 配置（用于获取行级 flush 阈值）
            profile_manager: Profile管理器
        """
        self.client = client
        self.logger = logger
        self.config = config
        self.profile_manager = profile_manager or ProfileManager()
        self._buffer = ""
    
    def stream_completion(self,
                          model: str,
                          messages: list,
                          temperature: float = 0.1,
                          max_tokens: int = 1000,
                          top_p: Optional[float] = None,
                          stop: Optional[list] = None,
                          frequency_penalty: float = 0.0,
                          presence_penalty: float = 0.0,
                          repetition_penalty: float = 1.0,
                          no_repeat_ngram_size: int = 0,
                          log_prefix: str = "模型输出",
                          watchdog_timeout_s: Optional[int] = None,
                          sentinel_prefix: Optional[str] = None,
                          enable_repeat_guard: bool = True,
                          max_retries: int = 3,
                          retry_delay_s: float = 2.0) -> Tuple[str, Dict[str, int]]:
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
            # 统一：在调用前漂亮打印完整 messages 到文件日志
            try:
                if self.logger:
                    pretty = self._format_messages(messages)
                    self.logger.info(f"{log_prefix} Prompt (messages):\n{pretty}", mode=UnifiedLogger.LogMode.BOTH)
            except Exception:
                pass
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
            # vLLM 扩展参数通过 extra_body 传递，避免 SDK 1.x 拦截
            if top_p is not None:
                req_kwargs["top_p"] = top_p
            extra_body = {}
            if repetition_penalty and repetition_penalty != 1.0:
                extra_body["repetition_penalty"] = repetition_penalty
            if no_repeat_ngram_size and no_repeat_ngram_size > 0:
                extra_body["no_repeat_ngram_size"] = no_repeat_ngram_size
            if stop:
                # 同步到 extra_body，保证后端终止词命中
                extra_body["stop"] = stop
            if extra_body:
                req_kwargs["extra_body"] = extra_body

            # 记录调用参数（避免打印过长内容，仅摘要 messages）
            try:
                messages_len = len(str(messages))
                messages_cnt = len(messages) if isinstance(messages, list) else 1
                stop_info = str(stop) if stop else "None"
                extra_keys = ",".join(sorted(extra_body.keys())) if extra_body else "None"
                log_msg = (
                    f"调用参数: model={model}, messages={messages_cnt} (chars={messages_len}), "
                    f"temperature={temperature:.3f}, top_p={top_p if top_p is not None else 'None'}, "
                    f"max_tokens={(max_tokens if isinstance(max_tokens, int) and max_tokens > 0 else 'None')}, "
                    f"freq_penalty={frequency_penalty:.2f}, presence_penalty={presence_penalty:.2f}, "
                    f"repetition_penalty={repetition_penalty}, no_repeat_ngram_size={no_repeat_ngram_size}, "
                    f"stop={stop_info}, extra_body_keys={extra_keys}"
                )
                if self.logger:
                    self.logger.info(log_msg)
            except Exception:
                pass

            # 重试逻辑
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    if attempt > 0:
                        if self.logger:
                            self.logger.warning(f"{log_prefix}: 第{attempt}次重试，延迟{retry_delay_s}秒...")
                        time.sleep(retry_delay_s)
                    
                    resp = self.client.chat.completions.create(**req_kwargs)
                    
                    result = ""
                    current_line = ""
                    flush_threshold = getattr(self.config, 'stream_line_flush_chars', 60) if self.config else 60
                    # 重复 token 截断控制
                    last_piece: Optional[str] = None
                    repeat_count: int = 0
                    start_time = time.time()
                    finish_reason = "unknown"  # 记录结束原因

                    def flush_current_line(reason: str) -> None:
                        nonlocal current_line
                        if current_line.strip():
                            if self.logger:
                                # 仅写文件
                                self.logger.debug(f"{log_prefix}: {current_line}", mode=UnifiedLogger.LogMode.FILE)
                        current_line = ""
                    
                    for chunk in resp:
                        # 检查是否有finish_reason
                        if hasattr(chunk.choices[0], 'finish_reason') and chunk.choices[0].finish_reason:
                            finish_reason = chunk.choices[0].finish_reason
                        
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
                            if enable_repeat_guard and len(piece.strip()) <= 1 and repeat_count > 40:
                                if self.logger:
                                    self.logger.warning(f"{log_prefix}: 检测到极短增量内容连续重复超过 20 次，提前截断流。")
                                finish_reason = "repetition_guard"
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

                            # 看门狗：时间超时
                            if watchdog_timeout_s is not None and watchdog_timeout_s > 0:
                                if time.time() - start_time > watchdog_timeout_s:
                                    if self.logger:
                                        self.logger.warning(f"{log_prefix}: 超过流式超时 {watchdog_timeout_s}s，提前停止读取。")
                                    finish_reason = "timeout"
                                    break

                            # 看门狗：长片段重复（检测尾部n-gram三连）
                            if enable_repeat_guard:
                                tail = result[-480:]
                                if len(tail) >= 120:
                                    n = 120
                                    a = tail[-n:]
                                    b = tail[-2*n:-n]
                                    c = tail[-3*n:-2*n]
                                    if a and a == b == c:
                                        if self.logger:
                                            self.logger.warning(f"{log_prefix}: 检测到尾部片段重复三次，提前停止读取。")
                                        finish_reason = "repetition_guard"
                                        break

                            # 哨兵：检测结论行
                            if sentinel_prefix and sentinel_prefix in result:
                                # 找到结论行后提前结束
                                finish_reason = "sentinel"
                                break
                    
                    # 收尾：统一用 flush 逻辑
                    if current_line:
                        flush_current_line('end')
                    
                    print()  # 换行
                    
                    # 计算token统计（这里简化处理，实际可能需要更精确的计算）
                    token_stats = {
                        'input_tokens': len(str(messages)) // 4,  # 粗略估算
                        'output_tokens': len(result) // 4,  # 粗略估算
                        'total_tokens': 0,
                        'max_tokens': max_tokens,
                        'finish_reason': finish_reason
                    }
                    token_stats['total_tokens'] = token_stats['input_tokens'] + token_stats['output_tokens']
                    
                    # 记录模型调用完成和token统计
                    if self.logger:
                        self.logger.info(f"模型调用完成，Token使用情况: {token_stats}")
                        self.logger.info(f"流式调用结束原因: {finish_reason}")
                    
                    return result, token_stats
                    
                except Exception as e:
                    last_exception = e
                    if self.logger:
                        self.logger.error(f"{log_prefix}: 第{attempt + 1}次尝试失败: {e}")
                    
                    # 如果是最后一次尝试，抛出异常
                    if attempt == max_retries:
                        if self.logger:
                            self.logger.error(f"{log_prefix}: 重试{max_retries}次后仍然失败，放弃重试")
                        raise e
            
            # 这里不应该到达，但为了安全起见
            if last_exception:
                raise last_exception
                
        except Exception as e:
            if self.logger:
                self.logger.error(f"{log_prefix}流式调用失败: {e}")
            raise e

    def stream_with_params(self, model: str, messages: list, params: GenerationParams) -> Tuple[str, Dict[str, int]]:
        """使用统一参数schema发起流式调用。"""
        return self.stream_completion(
            model=model,
            messages=messages,
            temperature=params.temperature,
            max_tokens=(params.max_tokens if isinstance(params.max_tokens, int) else 0),
            top_p=params.top_p,
            stop=params.stop,
            frequency_penalty=params.frequency_penalty,
            presence_penalty=params.presence_penalty,
            repetition_penalty=params.repetition_penalty,
            no_repeat_ngram_size=params.no_repeat_ngram_size,
            log_prefix=params.log_prefix,
            watchdog_timeout_s=params.watchdog_timeout_s,
            sentinel_prefix=params.sentinel_prefix,
            enable_repeat_guard=params.enable_repeat_guard,
            max_retries=getattr(self.config, 'max_retries', 3),
            retry_delay_s=getattr(self.config, 'retry_delay_s', 2.0),
        )

    # ===== Utilities =====
    def _format_messages(self, messages: list) -> str:
        try:
            lines: list[str] = []
            if not isinstance(messages, list):
                return str(messages)
            for i, m in enumerate(messages, start=1):
                role = m.get('role', 'user') if isinstance(m, dict) else 'user'
                content = m.get('content', '') if isinstance(m, dict) else str(m)
                lines.append(f"[{i}] role={role}")
                # 直接输出完整内容，避免可读性差的repr
                lines.append(str(content))
            return "\n".join(lines)
        except Exception:
            return str(messages)
