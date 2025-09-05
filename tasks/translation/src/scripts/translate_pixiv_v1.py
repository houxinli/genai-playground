#!/usr/bin/env python3
"""
批量翻译 Pixiv 下载的小说：
- 输入为带 YAML front matter 的 .txt（由 batch_download_v1.py 产出）
- 输出为同目录 {basename}_zh.txt

实现要点：
- 解析 YAML 头（简单边界识别），正文按段落划分（连续非空为段）
- 复用现有 test_translation.py 的翻译逻辑（通过本地 OpenAI 兼容端点）
- 支持文件/目录/通配符输入，增量跳过已存在 _zh.txt（除非 --overwrite）
- 记录完整 prompt/response 到 logs
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
import time
import re
import yaml
from pathlib import Path
from typing import List, Tuple, Optional, Dict

from openai import OpenAI
from openai import BadRequestError

import logging
from datetime import datetime


def setup_logging(log_path: Optional[Path] = None, stream_output: bool = True) -> logging.Logger:
    """设置统一的日志系统"""
    logger = logging.getLogger('translation')
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()  # 清除已有handlers

    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

    # 控制台输出
    if stream_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    # 文件输出（如果有log_path）
    if log_path:
        file_handler = logging.FileHandler(log_path, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger

def log_message(logger: Optional[logging.Logger], message: str, level: str = "INFO"):
    """统一的日志输出函数，支持logger为None的情况"""
    if level.upper() == "INFO":
        print(f"[INFO] {message}")
        if logger:
            logger.info(message)
    elif level.upper() == "WARNING":
        print(f"[WARNING] {message}")
        if logger:
            logger.warning(message)
    elif level.upper() == "ERROR":
        print(f"[ERROR] {message}")
        if logger:
            logger.error(message)
    elif level.upper() == "DEBUG":
        print(f"[DEBUG] {message}")
        if logger:
            logger.debug(message)
    else:
        print(f"[{level}] {message}")
        if logger:
            logger.log(getattr(logging, level.upper(), logging.INFO), message)

    # 强制刷新输出
    sys.stdout.flush()

# 兼容性函数
def setup_realtime_logging(log_path: Path, stream_output: bool = True) -> logging.Logger:
    """兼容性函数，调用新的setup_logging"""
    return setup_logging(log_path, stream_output)

def log_realtime(logger: logging.Logger, message: str, level: str = "INFO"):
    """兼容性函数，调用新的log_message"""
    log_message(logger, message, level)


def parse_yaml_front_matter(text: str) -> Optional[Dict]:
    """解析YAML front matter"""
    if not text.strip().startswith('---'):
        return None
    
    try:
        # 找到第一个和第二个 ---
        lines = text.split('\n')
        if len(lines) < 2:
            return None
        
        start_idx = None
        end_idx = None
        
        for i, line in enumerate(lines):
            if line.strip() == '---':
                if start_idx is None:
                    start_idx = i
                else:
                    end_idx = i
                    break
        
        if start_idx is None or end_idx is None:
            return None
        
        # 提取YAML部分
        yaml_text = '\n'.join(lines[start_idx + 1:end_idx])
        return yaml.safe_load(yaml_text)
    except Exception:
        return None

def get_repetition_config(strict_mode: bool = False) -> dict:
    """
    获取重复检测配置
    
    Args:
        strict_mode: 是否启用严格模式
        
    Returns:
        包含重复检测参数的字典
    """
    if strict_mode:
        return {
            "max_repeat_chars": 5,      # 严格模式：单字符最多重复5次
            "max_repeat_segments": 3,   # 严格模式：片段最多重复3次
            "stream_threshold": 5,      # 严格模式：流式检测阈值5
            "basic_char_threshold": 5,  # 严格模式：基础检测单字符阈值5
        }
    else:
        return {
            "max_repeat_chars": 10,     # 正常模式：单字符最多重复10次
            "max_repeat_segments": 5,   # 正常模式：片段最多重复5次  
            "stream_threshold": 8,      # 正常模式：流式检测阈值8
            "basic_char_threshold": 8,  # 正常模式：基础检测单字符阈值8
        }

def detect_and_truncate_repetition(text: str, max_repeat_chars: int = 10, max_repeat_segments: int = 5) -> str:
    """
    检测并截断重复模式，防止无限重复输出
    
    Args:
        text: 输入文本
        max_repeat_chars: 单个字符最大连续重复次数
        max_repeat_segments: 短片段最大重复次数
    
    Returns:
        截断重复后的文本
    """
    if not text or len(text) < 10:  # 降低最小长度要求
        return text
    
    # 1. 检测和截断单字符重复
    result = []
    i = 0
    # print(f"    开始检测单字符重复，文本长度: {len(text)}")  # 可选的调试输出
    
    while i < len(text):
        char = text[i]
        count = 1
        j = i + 1
        
        # 计算连续相同字符的数量
        while j < len(text) and text[j] == char:
            count += 1
            j += 1
        
        # 如果重复次数超过阈值，截断到阈值
        if count > max_repeat_chars:
            result.append(char * max_repeat_chars)
            print(f"    检测到字符 '{char}' 重复 {count} 次，截断到 {max_repeat_chars} 次")
            # 如果检测到严重重复，直接截断整个文本到这里
            if count > max_repeat_chars * 3:  # 如果重复超过阈值的3倍，可能是无限重复
                print(f"    检测到严重重复，截断整个文本")
                return ''.join(result)
        else:
            # if count > 1:  # 只在有重复时打印 - 注释掉以减少输出
            #     print(f"    字符 '{char}' 重复 {count} 次 (正常范围)")
            result.append(char * count)
        
        i = j
    
    text = ''.join(result)
    
    # 2. 检测和截断短片段重复
    # 从文本末尾开始检查，因为重复通常出现在末尾
    # print(f"    开始检测片段重复，文本长度: {len(text)}")  # 可选的调试输出
    if len(text) > 20:  # 降低检查阈值
        tail = text[-min(1000, len(text)):]  # 检查最后部分字符
        
        # 检测不同长度的重复片段
        for segment_len in range(5, min(101, len(tail) // 2 + 1), 5):  # 5到100字符的片段
            if segment_len > len(tail) // 2:
                continue
                
            segment = tail[-segment_len:]
            if not segment.strip():
                continue
                
            # 计算该片段在整个尾部重复的次数
            repeat_count = 0
            search_text = tail
            start_pos = 0
            
            # 使用简单的字符串计数方法
            while True:
                pos = search_text.find(segment, start_pos)
                if pos == -1:
                    break
                repeat_count += 1
                start_pos = pos + segment_len
            
            # 如果重复次数超过阈值，截断
            if repeat_count > max_repeat_segments:
                # 找到重复开始的位置
                repeat_start = len(text) - (repeat_count * segment_len)
                truncated_text = text[:repeat_start + (max_repeat_segments * segment_len)]
                print(f"    检测到片段重复 {repeat_count} 次（长度 {segment_len}），截断到 {max_repeat_segments} 次")
                print(f"    片段内容: '{segment}'")
                print(f"    原文长度: {len(text)}, 截断后长度: {len(truncated_text)}")
                return truncated_text
            # elif repeat_count > 1:  # 注释掉以减少输出
            #     print(f"    发现片段重复 {repeat_count} 次（长度 {segment_len}），在正常范围内")
    
    return text

def clean_output_text(text: str) -> str:
    """清理输出文本，去除思考部分等"""
    if not text or not text.strip():
        return text
    
    # 首先检测和截断重复模式
    text = detect_and_truncate_repetition(text)
    
    # 去除 <think>...</think> 部分
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    
    # 去除其他可能的思考标记
    text = re.sub(r'（思考：.*?）', '', text, flags=re.DOTALL)
    text = re.sub(r'（注：.*?）', '', text, flags=re.DOTALL)
    
    # 清理多余的空行，但保留有意义的空行
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        if line.strip():
            cleaned_lines.append(line)
        elif cleaned_lines and cleaned_lines[-1].strip():  # 保留有意义的空行
            cleaned_lines.append(line)
    
    result = '\n'.join(cleaned_lines).strip()
    return result if result else text  # 如果清理后为空，返回原文

def check_translation_quality_with_llm(original_text: str, translated_text: str, model: str = "Qwen/Qwen3-32B", bilingual: bool = False) -> Tuple[bool, str]:
    """
    使用大模型检查翻译质量，特别关注最后部分的完整性
    支持bilingual和单语模式
    返回: (is_good, reason)
    """
    if not translated_text or not translated_text.strip():
        return False, "翻译结果为空"
    
    # 提取原文和翻译的最后部分（约800字符）
    original_end = original_text[-800:] if len(original_text) > 800 else original_text
    translated_end = translated_text[-800:] if len(translated_text) > 800 else translated_text
    
    # 根据模式调整检测提示词
    if bilingual:
        prompt = f"""检查以下日语原文最后部分和中文翻译最后部分（bilingual对照模式），判断翻译是否完整正确。

原文最后部分：
{original_end}

翻译最后部分（bilingual格式）：
{translated_end}

判断标准：
1. 翻译是否完整（没有遗漏原文内容）
2. 翻译是否准确（没有错误）
3. 是否正常结束（没有"以下省略"等标记）
4. bilingual格式是否正确（日语原文后跟中文译文）

如果翻译完整正确，回复：GOOD
如果有问题，回复：BAD

只回复GOOD或BAD。"""
    else:
        prompt = f"""检查以下日语原文最后部分和中文翻译最后部分，判断翻译是否完整正确。

原文最后部分：
{original_end}

翻译最后部分：
{translated_end}

判断标准：
1. 翻译是否完整（没有遗漏原文内容）
2. 翻译是否准确（没有错误）
3. 是否正常结束（没有"以下省略"等标记）

如果翻译完整正确，回复：GOOD
如果有问题，回复：BAD

只回复GOOD或BAD。"""

    try:
        client = OpenAI(base_url="http://localhost:8000/v1", api_key="dummy")
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=200,
        )
        result = resp.choices[0].message.content.strip()
        
        if result.upper().startswith("GOOD"):
            mode_text = "bilingual对照模式" if bilingual else "单语模式"
            return True, f"大模型评估：{mode_text}最后部分翻译质量良好"
        elif result.upper().startswith("BAD"):
            reason = result[3:].strip() if len(result) > 3 else "大模型评估：最后部分翻译质量不佳"
            return False, reason
        else:
            # 如果模型回复不明确，使用基础检测
            return check_translation_quality_basic(original_text, translated_text, bilingual)
            
    except Exception as e:
        print(f"    大模型检测失败: {e}，使用基础检测")
        return check_translation_quality_basic(original_text, translated_text, bilingual)

def check_translation_quality_basic(original_text: str, translated_text: str, bilingual: bool = False) -> Tuple[bool, str]:
    """
    基础翻译质量检测（作为大模型检测的备选）
    """
    if not translated_text or not translated_text.strip():
        return False, "翻译结果为空"
    
    # 1. 检查长度比例（翻译结果应该至少是原文的20%）
    original_len = len(original_text.strip())
    translated_len = len(translated_text.strip())
    
    if translated_len < original_len * 0.2:
        return False, f"翻译结果太短: {translated_len}/{original_len} ({translated_len/original_len:.1%})"
    
    # 2. 检查是否包含明显的翻译错误
    error_patterns = [
        r'（以下省略）',  # 省略标记
        r'\[TO BE CONTINUED\]',  # 未完待续
        r'\[\.\.\.\]',  # 省略号
        r'（此处省略',  # 省略说明
        r'（注：',  # 注释
        r'完整版请参考',  # 完整版引用
        r'由于文本长度限制',  # 长度限制说明
        r'内容性质原因',  # 内容原因
        r'仅展示部分',  # 部分展示
        r'省略大量重复',  # 重复省略
        r'最终段落',  # 最终段落
        r'（翻译结束）',  # 翻译结束
        r'<think>',  # 思考标记
        r'</think>',  # 思考标记结束
    ]
    
    for pattern in error_patterns:
        if re.search(pattern, translated_text, re.IGNORECASE):
            return False, f"包含错误模式: {pattern}"
    
    # 3. 检查是否包含大量日语原文（bilingual模式下放宽标准）
    japanese_chars = len(re.findall(r'[\u3040-\u309f\u30a0-\u30ff]', translated_text))
    total_chars = len(translated_text)
    
    # bilingual模式下，由于包含原文，日语比例会更高，放宽到50%
    max_japanese_ratio = 0.5 if bilingual else 0.3
    
    if japanese_chars > total_chars * max_japanese_ratio:
        return False, f"包含过多日语原文: {japanese_chars}/{total_chars} ({japanese_chars/total_chars:.1%})"
    
    # 4. 检查是否包含大量重复字符（如问号、感叹号等）
    # 检查最后100个字符中是否有超过50%的重复字符
    last_100_chars = translated_text.strip()[-100:] if len(translated_text.strip()) >= 100 else translated_text.strip()
    if len(last_100_chars) >= 50:
        char_counts = {}
        for char in last_100_chars:
            char_counts[char] = char_counts.get(char, 0) + 1
        
        # 找出出现最多的字符
        most_common_char = max(char_counts.items(), key=lambda x: x[1])
        if most_common_char[1] > len(last_100_chars) * 0.5:  # 超过50%是同一个字符
            return False, f"结尾包含大量重复字符: {most_common_char[0]} ({most_common_char[1]}/{len(last_100_chars)})"
    
    # 5. 检查是否以不完整的句子结尾
    if not translated_text.strip().endswith(('。', '！', '？', '…', '"', '"', ''', ''', '）', '】', '」', '』')):
        last_sentence = translated_text.strip().split('\n')[-1]
        if len(last_sentence) > 20 and not any(last_sentence.endswith(end) for end in ('。', '！', '？', '…', '"', '"', ''', ''', '）', '】', '」', '』')):
            return False, "句子不完整结尾"
    
    return True, "基础检测：翻译质量良好"

def clean_output_text(text: str) -> str:
    if not text or not text.strip():
        return text
    
    # 去除 <think>...</think> 部分
    import re
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    
    # 去除其他可能的思考标记
    text = re.sub(r'（思考：.*?）', '', text, flags=re.DOTALL)
    text = re.sub(r'（注：.*?）', '', text, flags=re.DOTALL)
    
    # 清理多余的空行，但保留有意义的空行
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        if line.strip():
            cleaned_lines.append(line)
        elif cleaned_lines and cleaned_lines[-1].strip():  # 保留有意义的空行
            cleaned_lines.append(line)
    
    result = '\n'.join(cleaned_lines).strip()
    return result if result else text  # 如果清理后为空，返回原文

def split_text_by_lines(text: str, max_chars: int, overlap_chars: int) -> List[str]:
    """按行分割文本，确保整行不被截断"""
    lines = text.split('\n')
    chunks = []
    current_chunk = []
    current_length = 0
    
    for line in lines:
        line_length = len(line) + 1  # +1 for newline
        
        # 如果当前行加上当前块会超出限制
        if current_length + line_length > max_chars and current_chunk:
            # 保存当前块
            chunk_text = '\n'.join(current_chunk)
            chunks.append(chunk_text)
            
            # 计算重叠部分（从当前块的末尾取overlap_chars字符）
            if overlap_chars > 0 and len(chunk_text) > overlap_chars:
                overlap_text = chunk_text[-overlap_chars:]
                # 找到重叠文本中最后一个完整的行
                last_newline = overlap_text.rfind('\n')
                if last_newline > 0:
                    overlap_text = overlap_text[last_newline + 1:]
                current_chunk = [overlap_text] if overlap_text else []
                current_length = len(overlap_text)
            else:
                current_chunk = []
                current_length = 0
        
        # 添加当前行到块中
        current_chunk.append(line)
        current_length += line_length
    
    # 添加最后一个块
    if current_chunk:
        chunks.append('\n'.join(current_chunk))
    
    return chunks


def load_few_shot_samples(sample_file: Path) -> List[Tuple[str, str]]:
    """从 sample.txt 加载 few-shot 示例"""
    if not sample_file.exists():
        return []
    
    try:
        content = sample_file.read_text(encoding="utf-8")
        samples = []
        lines = content.split('\n')
        i = 0
        while i < len(lines):
            if lines[i].strip() == 'input:':
                # 找到 input 开始
                input_lines = []
                i += 1
                while i < len(lines) and lines[i].strip() != 'output:':
                    input_lines.append(lines[i])
                    i += 1
                
                if i < len(lines) and lines[i].strip() == 'output:':
                    # 找到 output 开始
                    output_lines = []
                    i += 1
                    while i < len(lines) and (lines[i].strip() or not lines[i].strip().startswith('input:')):
                        if lines[i].strip().startswith('input:'):
                            break
                        output_lines.append(lines[i])
                        i += 1
                    
                    if input_lines and output_lines:
                        input_text = '\n'.join(input_lines).strip()
                        output_text = '\n'.join(output_lines).strip()
                        samples.append((input_text, output_text))
                else:
                    i += 1
            else:
                i += 1
        
        return samples
    except Exception as e:
        print(f"WARN: 无法加载 few-shot 示例: {e}")
        return []


def split_yaml_and_body(text: str) -> Tuple[str, str]:
    s = text.lstrip()
    if not s.startswith("---\n"):
        return "", text
    # 找到第二个 '---' 行
    parts = s.split("\n---\n", 1)
    if len(parts) == 2:
        yaml_part = parts[0][4:]  # 去掉开头的 '---\n'
        body = parts[1]
        return yaml_part, body.lstrip("\n")
    return "", text


def parse_yaml_minimal(yaml_text: str) -> Dict[str, str]:
    meta: Dict[str, str] = {}
    for line in yaml_text.splitlines():
        if not line.strip():
            continue
        if ":" not in line:
            continue
        try:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
        except ValueError:
            continue
    return meta


def split_paragraphs(body: str) -> List[str]:
    lines = body.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    paras: List[str] = []
    buf: List[str] = []
    for ln in lines:
        if ln.strip() == "":
            if buf:
                paras.append("\n".join(buf).strip())
                buf = []
        else:
            buf.append(ln)
    if buf:
        paras.append("\n".join(buf).strip())
    return paras


def translate_with_local_llm(text: str, model: str, temperature: float, max_tokens: int, terminology: Optional[str] = None, stop: Optional[List[str]] = None, frequency_penalty: Optional[float] = None, presence_penalty: Optional[float] = None, few_shot_samples: Optional[List[Tuple[str, str]]] = None, max_context_length: Optional[int] = None, preface_file: Optional[str] = None, bilingual: bool = False, stream: bool = False, logger: Optional[logging.Logger] = None) -> Tuple[str, str, Dict[str, int]]:
    # 组装带术语表的提示词
    if preface_file and Path(preface_file).exists():
        with open(preface_file, 'r', encoding='utf-8') as f:
            preface = f.read().strip() + "\n"
    else:
        # 如果没有提供preface_file，使用默认的翻译指令
        if bilingual:
            preface = """请将以下日语文本忠实翻译为中文，并按照示例格式输出双语对照格式：
- 输出格式：请严格按照示例格式，逐行输出日语原文+中文译文对照格式，即每行日语原文后紧跟对应的中文译文；
- 严格保持原文的分段与分行，不合并、不省略、不添加解释；
- 对话与引号样式对齐，空行位置保持不变；
- 拟声词翻译规则：将日语拟声词翻译为对应的中文拟声词，如「どびゅびゅっ」→「噗呲呲」；若遇到难以对应到中文发音的孤立音节（如「っ」「ん」等），可适当省略，仅保留能对应的部分；
- 断点词处理：对于「せ・ん・せ」这种带断点的词，先翻译完整词（如「先生」→「老师」），然后在中文词上添加断点（如「老・师」）；
- 仅输出双语对照格式的翻译结果，不要额外说明或思考内容。\n\n"""
        else:
            preface = """请将以下日语文本忠实翻译为中文：
- 严格保持原文的分段与分行，不合并、不省略、不添加解释；
- 对话与引号样式对齐，空行位置保持不变；
- 拟声词翻译规则：将日语拟声词翻译为对应的中文拟声词；
- 断点词处理：对于带断点的词，先翻译完整词，然后在中文词上添加断点；
- 仅输出翻译结果，不要额外说明或思考内容。\n\n"""
    if terminology:
        preface += "以下是术语对照表，请严格参照：\n" + terminology.strip() + "\n\n"
    
    prompt = preface
    if few_shot_samples:
        prompt += "\n\nFew-shot 示例：\n"
        for i, (input_text, output_text) in enumerate(few_shot_samples, 1):
            prompt += f"示例 {i}:\n输入:\n{input_text}\n\n输出:\n{output_text}\n\n"
        prompt += "请根据这些示例，忠实地翻译以下文本。\n\n"
    
    prompt += "原文：\n\n" + text + "\n\n翻译结果："
    
    # 估算输入tokens（粗略）：按字符数 * 0.7
    estimated_input_tokens = int(len(prompt) * 0.7)
    log_message(logger, f"调用模型，prompt长度: {len(prompt)}")
    log_message(logger, f"完整prompt:\n{prompt}")
    client = OpenAI(base_url="http://localhost:8000/v1", api_key="dummy")
    kwargs = {}
    if stop:
        kwargs["stop"] = stop
    if frequency_penalty is not None:
        kwargs["frequency_penalty"] = frequency_penalty
    if presence_penalty is not None:
        kwargs["presence_penalty"] = presence_penalty
    # vLLM 端通常要求显式 max_tokens；当 <=0 时使用安全大值
    chosen_max_tokens = max_tokens
    if not isinstance(chosen_max_tokens, int) or chosen_max_tokens <= 0:
        # 动态计算合适的 max_tokens，确保不超过模型的最大上下文长度
        # 如果没有传入max_context_length，则根据模型名称推断默认值
        if max_context_length is None:
            if "32B" in model and "AWQ" not in model:
                # 完整32B模型：32768 tokens
                max_context_length = 32768
            else:
                # AWQ或其他模型：40960 tokens
                max_context_length = 40960
        
        # 为了安全起见，我们使用更保守的估算
        # 预留 2000 tokens 作为安全边界
        safe_max_tokens = max_context_length - int(estimated_input_tokens) - 2000
        chosen_max_tokens = max(1000, safe_max_tokens)  # 至少保留 1000 tokens
        print(f"    动态计算 max_tokens: {chosen_max_tokens} (基于输入长度 {len(prompt)}, 估算输入tokens: {estimated_input_tokens}, 模型上下文长度: {max_context_length})")
    # 估计输出tokens上限（含思考+译文）：取 chosen_max_tokens
    token_meta: Dict[str, int] = {
        "estimated_input_tokens": int(estimated_input_tokens),
        "estimated_output_tokens": int(max(0, chosen_max_tokens)),
        "max_context_length": int(max_context_length if max_context_length else 0),
        "used_max_tokens": int(chosen_max_tokens),
        "prompt_chars": len(prompt),
        "text_chars": len(text),
    }
    try:
        if stream:
            log_message(logger, f"开始流式调用...")
            result = ""
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=chosen_max_tokens,
                stream=True,
                **kwargs,
            )
            
            # 流式重复检测参数（根据严格模式调整）
            repetition_buffer = ""
            max_buffer_size = 500  # 保留最近500字符用于检测
            # 根据模型参数中的严格模式调整阈值
            # 注意：这里我们需要从外层传递strict_mode参数，暂时使用默认值
            repetition_threshold = 8  # 连续重复阈值，更严格
            
            for chunk in resp:
                if chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    
                    # 检测实时重复
                    temp_result = result + content
                    repetition_buffer += content
                    
                    # 保持buffer大小
                    if len(repetition_buffer) > max_buffer_size:
                        repetition_buffer = repetition_buffer[-max_buffer_size:]
                    
                    # 检测单字符重复
                    should_stop = False
                    if len(repetition_buffer) >= repetition_threshold:
                        # 检查最后的字符是否重复过多
                        last_char = repetition_buffer[-1]
                        consecutive_count = 0
                        for i in range(len(repetition_buffer) - 1, -1, -1):
                            if repetition_buffer[i] == last_char:
                                consecutive_count += 1
                            else:
                                break
                        
                        if consecutive_count >= repetition_threshold:
                            print(f"\n[检测到重复输出，停止生成] 字符 '{last_char}' 连续重复 {consecutive_count} 次")
                            should_stop = True
                    
                    if should_stop:
                        break
                    
                    result += content
                    # 流式输出只在控制台显示，不记录到日志文件
                    print(content, end="", flush=True)
            print()  # 换行
            result = result.strip()
            # 在流式输出完成后，在控制台显示完整的翻译结果
            log_message(logger, f"翻译完成，结果长度: {len(result)}")
            # 在控制台显示前几行作为预览
            lines = result.split('\n')
            preview_lines = lines[:10]  # 显示前10行
            log_message(logger, f"翻译结果预览（前10行）:")
            for line in preview_lines:
                log_message(logger, f"    {line}")
            if len(lines) > 10:
                log_message(logger, f"    ... (还有 {len(lines) - 10} 行)")
        else:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=chosen_max_tokens,
                **kwargs,
            )
            result = resp.choices[0].message.content.strip()
        
        log_message(logger, f"模型返回，结果长度: {len(result)}")
        
        # 计算实际使用的token数
        actual_output_tokens = int(len(result) * 0.7)  # 粗略估算
        total_tokens = estimated_input_tokens + actual_output_tokens
        
        # 更新token_meta
        token_meta.update({
            "actual_output_tokens": actual_output_tokens,
            "total_tokens": total_tokens,
            "result_chars": len(result),
            "used_max_tokens": total_tokens,  # 修正：实际使用的max_tokens应该是总tokens
        })
        
        return result, prompt, token_meta
    except Exception as e:
        log_message(logger, f"模型调用失败: {e}", "ERROR")
        raise


def looks_bad_output(text: str, original_text: str = "") -> bool:
    if not text:
        print("    looks_bad_output: 文本为空")
        return True
    
    print(f"    looks_bad_output: 检查文本，长度={len(text)}")
    
    # 检测重复模式（更宽松）
    tail = text[-1000:]  # 检查尾部1000字符（之前是800）
    
    # 1. 检测连续重复的短片段（长度10-100重复3次以上，之前是5-50重复2次）
    for w in range(10, 101, 10):
        if w > len(tail):
            continue
        seg = tail[-w:]
        if seg and tail.count(seg) >= 3:  # 从2次改为3次
            print(f"    looks_bad_output: 检测到重复片段，长度={w}")
            return True
    
    # 2. 检测单字符过长重复（超过8次，恢复更严格的检测）
    for ch in set(tail):
        if ch * 8 in tail:  # 恢复为8次，更严格检测
            print(f"    looks_bad_output: 检测到单字符重复: {ch}")
            return True
    
    # 3. 检测异常结尾模式（保持不变）
    bad_endings = [
        "未完待续", "[TO BE CONTINUED]", "[...]", "（此处省略", "（注：", 
        "完整版请参考", "由于文本长度限制", "内容性质原因", "仅展示部分",
        "省略大量重复", "最终段落", "---", "###", "***", "（翻译结束）"
    ]
    if any(bad in tail for bad in bad_endings):
        print(f"    looks_bad_output: 检测到异常结尾")
        return True
    
    # 4. 检测非中文/日文字符过多（阈值从30%改为50%）
    non_cjk = sum(1 for c in tail if not ('\u4e00' <= c <= '\u9fff' or '\u3040' <= c <= '\u309f' or '\u30a0' <= c <= '\u30ff' or c in '，。！？；：""''（）【】…—'))
    if non_cjk > len(tail) * 0.5:  # 从0.3改为0.5
        print(f"    looks_bad_output: 非CJK字符过多: {non_cjk}/{len(tail)}")
        return True
    
    # 5. 检测标点符号缺失（阈值从50改为100）
    cjk_only = ''.join(c for c in tail if '\u4e00' <= c <= '\u9fff')
    if len(cjk_only) > 100 and not any(p in tail for p in '，。！？；：'):  # 从50改为100
        print(f"    looks_bad_output: 标点符号缺失")
        return True
    
    # 6. 检测翻译完整性（阈值从30%改为20%）
    if original_text:
        original_len = len(original_text.strip())
        translated_len = len(text.strip())
        
        if translated_len < original_len * 0.2:  # 从0.3改为0.2
            print(f"    looks_bad_output: 译文太短: {translated_len}/{original_len}")
            return True
        
        # 如果译文突然结束，没有明显的结尾标记
        if not text.strip().endswith(('。', '！', '？', '…', '"', '"', ''', ''', '）', '】')):
            last_sentence = text.strip().split('\n')[-1]
            if len(last_sentence) > 20 and not any(last_sentence.endswith(end) for end in ('。', '！', '？', '…', '"', '"', ''', ''', '）', '】')):  # 从10改为20
                print(f"    looks_bad_output: 句子突然结束")
                return True
    
    print("    looks_bad_output: 文本检查通过")
    return False


def translate_chunk_with_retry(
    chunk_text: str,
    model: str,
    temperature: float,
    max_tokens: int,
    terminology_txt: Optional[str],
    stop: Optional[List[str]],
    frequency_penalty: Optional[float],
    presence_penalty: Optional[float],
    retries: int,
    retry_wait: float,
    few_shot_samples: Optional[List[Tuple[str, str]]],
    max_context_length: Optional[int] = None,
    preface_file: Optional[str] = None,
    bilingual: bool = False,
    stream: bool = False,
    logger: Optional[logging.Logger] = None,
    chunk_index: Optional[int] = None,
) -> Tuple[str, str, bool, Dict[str, int]]:
    """返回 (output, prompt, ok)。ok=False 表示建议降级分块/或重试失败。"""
    last_err = None
    # 预先计算token_meta，以便在失败时也能返回有效信息
    estimated_input_tokens = int(len(chunk_text) * 0.7)
    if max_context_length is None:
        if "32B" in model and "AWQ" not in model:
            max_context_length = 32768
        else:
            max_context_length = 40960
    
    base_token_meta = {
        "estimated_input_tokens": estimated_input_tokens,
        "estimated_output_tokens": 0,
        "max_context_length": max_context_length,
        "actual_output_tokens": 0,
        "total_tokens": estimated_input_tokens,
        "used_max_tokens": estimated_input_tokens,
        "prompt_chars": len(chunk_text),
        "text_chars": len(chunk_text),
        "result_chars": 0,
    }
    
    chunk_info = f"块 {chunk_index}" if chunk_index is not None else "块"
    
    for attempt in range(1, max(1, retries) + 1):
        try:
            out, prompt, token_meta = translate_with_local_llm(
                chunk_text,
                model,
                temperature,
                max_tokens,
                terminology_txt,
                stop=stop,
                frequency_penalty=frequency_penalty,
                presence_penalty=presence_penalty,
                few_shot_samples=few_shot_samples,
                max_context_length=max_context_length,
                preface_file=preface_file,
                bilingual=bilingual,
                stream=stream,
                logger=logger,
            )
            
            # 进行质量检测
            if out and out.strip():
                log_message(logger, f"    对{chunk_info}进行质量检测...", "INFO")
                is_good, reason = check_translation_quality_with_llm(
                    chunk_text, out, model, bilingual=bilingual
                )
                
                if is_good:
                    log_message(logger, f"    {chunk_info}质量检测通过: {reason}", "INFO")
                    return out, prompt, True, token_meta
                else:
                    log_message(logger, f"    {chunk_info}质量检测失败: {reason}", "WARNING")
                    if attempt < retries:
                        log_message(logger, f"    质量不佳，重试{chunk_info} (尝试 {attempt + 1}/{retries})", "WARNING")
                        time.sleep(retry_wait)
                        continue
                    else:
                        log_message(logger, f"    {chunk_info}质量不佳但已达到最大重试次数，返回结果", "WARNING")
                        return out, prompt, True, token_meta
            else:
                log_message(logger, f"    {chunk_info}翻译结果为空", "WARNING")
                if attempt < retries:
                    log_message(logger, f"    结果为空，重试{chunk_info} (尝试 {attempt + 1}/{retries})", "WARNING")
                    time.sleep(retry_wait)
                    continue
                else:
                    log_message(logger, f"    {chunk_info}多次重试仍为空，返回失败", "ERROR")
                    return "", "", False, base_token_meta
            
        except BadRequestError as e:  # 例如上下文溢出
            last_err = e
            msg = str(e).lower()
            if any(k in msg for k in ["context", "too many tokens", "maximum context length", "max_tokens must be"]):
                # 上下文相关错误，提示外层降级为分段
                log_message(logger, f"    {chunk_info}上下文溢出错误: {e}", "ERROR")
                return "", "", False, base_token_meta
            log_message(logger, f"    {chunk_info}重试 {attempt}/{retries}: BadRequestError: {e}", "WARNING")
            time.sleep(retry_wait)
            continue
        except Exception as e:
            last_err = e
            log_message(logger, f"    {chunk_info}重试 {attempt}/{retries}: Exception: {e}", "WARNING")
            time.sleep(retry_wait)
            continue
    
    # 多次失败，返回基础token信息
    log_message(logger, f"    {chunk_info}所有重试都失败了，最后错误: {last_err}", "ERROR")
    return "", "", False, base_token_meta


def create_bilingual_output(original_text: str, translated_chunks: List[str]) -> str:
    """创建对照模式输出：逐行日语原文 + 中文译文"""
    # 解析YAML front matter
    article_info = parse_yaml_front_matter(original_text)
    
    # 分离YAML部分和正文部分
    original_lines = original_text.split('\n')
    full_translation = '\n\n'.join(translated_chunks)
    translated_lines = full_translation.split('\n')
    
    # 找到YAML结束位置
    yaml_end_idx = -1
    if article_info:
        for i, line in enumerate(original_lines):
            if line.strip() == '---' and i > 0:  # 第二个---
                yaml_end_idx = i
                break
    
    bilingual_lines = []
    
    # 处理YAML部分（如果有）
    if yaml_end_idx > 0:
        # YAML部分：原文行 + 译文行交错
        for i in range(yaml_end_idx + 1):
            # 添加原文行
            if i < len(original_lines):
                original_line = original_lines[i]
                bilingual_lines.append(original_line)
            else:
                bilingual_lines.append("")
            
            # 添加译文行
            if i < len(translated_lines):
                translated_line = translated_lines[i]
                bilingual_lines.append(translated_line)
            else:
                bilingual_lines.append("")
    
    # 处理正文部分
    if yaml_end_idx >= 0:
        # 从YAML结束后开始处理正文
        original_body_lines = original_lines[yaml_end_idx + 1:]
        # 确保翻译文本也有对应的正文部分
        if len(translated_lines) > yaml_end_idx:
            translated_body_lines = translated_lines[yaml_end_idx + 1:]
        else:
            # 如果翻译文本没有YAML部分，直接使用全部翻译文本
            translated_body_lines = translated_lines
    else:
        # 没有YAML，直接处理全部
        original_body_lines = original_lines
        translated_body_lines = translated_lines
    
    # 正文部分：原文行 + 译文行交错
    max_body_lines = max(len(original_body_lines), len(translated_body_lines))
    for i in range(max_body_lines):
        # 添加原文行
        if i < len(original_body_lines):
            original_line = original_body_lines[i]
            bilingual_lines.append(original_line)
        else:
            bilingual_lines.append("")
        
        # 添加译文行
        if i < len(translated_body_lines):
            translated_line = translated_body_lines[i]
            bilingual_lines.append(translated_line)
        else:
            bilingual_lines.append("")
    
    return '\n'.join(bilingual_lines)


def process_file(path: Path, model: str, temperature: float, max_tokens: int, overwrite: bool, log_dir: Path, terminology_file: Optional[Path], chunk_size_chars: int, stop: Optional[List[str]], frequency_penalty: Optional[float], presence_penalty: Optional[float], mode: str, overlap_chars: int, retries: int, retry_wait: float, fallback_on_context: bool, few_shot_samples: Optional[List[Tuple[str, str]]], max_context_length: Optional[int] = None, preface_file: Optional[str] = None, bilingual: bool = False, stream: bool = False, realtime_log: bool = False, no_llm_check: bool = False) -> None:
    # 设置日志
    logger = None
    if realtime_log:
        # 提前定义log_path
        log_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d-%H%M%S")
        log_path = log_dir / f"translation_{path.stem}_{ts}.log"
        logger = setup_logging(log_path, stream_output=True)
    else:
        logger = setup_logging(stream_output=True)
    # 入口处进行文件类型判断与清理，防止跑偏
    name = path.name
    stem = path.stem
    # 1) 若是重复的 _bilingual_bilingual.txt，直接删除后返回
    if name.endswith("_bilingual_bilingual.txt"):
        try:
            path.unlink()
            log_message(logger, f"DELETE duplicate: {path}")
        except Exception as e:
            log_message(logger, f"WARN 删除失败: {path} -> {e}", "WARNING")
        return

    # 2) 若是 *_bilingual.txt / *_awq_bilingual.txt -> 仅质量检测，不合格则删除，合格则跳过
    if name.endswith("_bilingual.txt") or name.endswith("_awq_bilingual.txt"):
        original_path = None
        if name.endswith("_bilingual.txt"):
            original_path = path.with_name(stem.replace("_bilingual", "") + ".txt")
        elif name.endswith("_awq_bilingual.txt"):
            original_path = path.with_name(stem.replace("_awq_bilingual", "") + ".txt")
        if original_path and original_path.exists():
            try:
                original_text = original_path.read_text(encoding="utf-8", errors="ignore")
                translated_text = path.read_text(encoding="utf-8", errors="ignore")
                if no_llm_check:
                    ok, reason = check_translation_quality_basic(original_text, translated_text, bilingual=True)
                else:
                    ok, reason = check_translation_quality_with_llm(original_text, translated_text, model, bilingual=True)
                if ok:
                    log_message(logger, f"KEEP {path} ({reason})")
                else:
                    log_message(logger, f"DELETE low-quality: {path} ({reason})")
                    try:
                        path.unlink()
                    except Exception as e:
                        log_message(logger, f"WARN 删除失败: {path} -> {e}", "WARNING")
                return
            except Exception as e:
                log_message(logger, f"WARN 质量检测失败: {path} -> {e}", "WARNING")
                return
        else:
            log_message(logger, f"SKIP no-original: {path}")
            return

    # 3) 若包含 _zh（或 _awq_zh），忽略
    if name.endswith("_zh.txt") or name.endswith("_awq_zh.txt") or "_zh_" in name:
        log_message(logger, f"SKIP zh file: {path}")
        return

    # 4) 原文：若已存在任一 bilingual（或 awq_bilingual），检查质量后决定是否跳过
    possible_bi = [
        path.with_name(stem + "_bilingual.txt"),
        path.with_name(stem + "_awq_bilingual.txt"),
    ]
    existing_bilingual_file = None
    for bi in possible_bi:
        if bi.exists():
            existing_bilingual_file = bi
            break
    
    if existing_bilingual_file and not overwrite:
        try:
            original_text = path.read_text(encoding="utf-8", errors="ignore")
            translated_text = existing_bilingual_file.read_text(encoding="utf-8", errors="ignore")
            print(f"    检查现有bilingual翻译文件质量: {existing_bilingual_file.name}")
            if no_llm_check:
                is_good, reason = check_translation_quality_basic(original_text, translated_text, bilingual=True)
            else:
                is_good, reason = check_translation_quality_with_llm(original_text, translated_text, model, bilingual=True)
            if is_good:
                print(f"SKIP {existing_bilingual_file} (翻译质量良好: {reason})")
                return
            else:
                print(f"DELETE low-quality: {existing_bilingual_file} ({reason})")
                try:
                    existing_bilingual_file.unlink()
                except Exception as e:
                    print(f"WARN 删除失败: {existing_bilingual_file} -> {e}")
                # 删除后继续翻译
        except Exception as e:
            print(f"WARN 质量检测失败: {existing_bilingual_file} -> {e}")
            # 如果检查失败，继续翻译
    # 根据模型和模式区分输出文件名
    model_upper = (model or "").upper()
    if bilingual:
        zh_suffix = "_awq_bilingual.txt" if "AWQ" in model_upper else "_bilingual.txt"
    else:
        zh_suffix = "_awq_zh.txt" if "AWQ" in model_upper else "_zh.txt"
    zh_path = path.with_name(path.stem + zh_suffix)
    
    # 检查是否已存在翻译文件且质量良好（非bilingual模式）
    if not bilingual and zh_path.exists() and not overwrite:
        try:
            existing_translation = zh_path.read_text(encoding="utf-8", errors="ignore")
            print(f"    检查现有翻译文件质量...")
            # 先读取原文
            raw_text = path.read_text(encoding="utf-8", errors="ignore")
            if no_llm_check:
                is_good, reason = check_translation_quality_basic(raw_text, existing_translation)
            else:
                is_good, reason = check_translation_quality_with_llm(raw_text, existing_translation, model)
            if is_good:
                print(f"SKIP {zh_path} (翻译质量良好: {reason})")
                return
            else:
                print(f"REWRITE {zh_path} (翻译质量不佳: {reason})")
        except Exception as e:
            print(f"WARN 检查现有翻译文件失败: {e}")
            # 如果检查失败，继续翻译
    
    # 读取原文
    raw_text = path.read_text(encoding="utf-8", errors="ignore")
    if not raw_text.strip():
        log_message(logger, f"WARN empty file: {path}", "WARNING")
        return
    
    # 解析YAML front matter获取文章信息
    article_info = parse_yaml_front_matter(raw_text)
    if article_info:
        log_message(logger, f"📖 文章信息:")
        log_message(logger, f"   标题: {article_info.get('title', '未知')}")
        log_message(logger, f"   作者: {article_info.get('author', {}).get('name', '未知')}")
        log_message(logger, f"   系列: {article_info.get('series', {}).get('title', '无系列')}")
        log_message(logger, f"   创建时间: {article_info.get('create_date', '未知')}")
        log_message(logger, f"   原文长度: {len(raw_text)} 字符")
        log_message(logger, f"   标签: {', '.join(article_info.get('tags', []))}")
    else:
        log_message(logger, f"📖 文章信息: 无法解析YAML front matter")
        log_message(logger, f"   原文长度: {len(raw_text)} 字符")
    
    log_message(logger, f"🔧 翻译配置:")
    log_message(logger, f"   模型: {model}")
    log_message(logger, f"   模式: {mode}")
    log_message(logger, f"   对照模式: {bilingual}")
    log_message(logger, f"   流式输出: {stream}")
    log_message(logger, f"   实时日志: {realtime_log}")
    log_message(logger, f"   块大小: {chunk_size_chars} 字符")
    log_message(logger, f"   重叠大小: {overlap_chars} 字符")
    log_message(logger, f"   重试次数: {retries}")
    log_message(logger, f"   重试等待: {retry_wait} 秒")
    log_message(logger, f"   上下文长度: {max_context_length or '默认'}")
    log_message(logger, f"   温度: {temperature}")
    log_message(logger, f"   频率惩罚: {frequency_penalty}")
    log_message(logger, f"   存在惩罚: {presence_penalty}")
    log_message(logger, f"   术语文件: {terminology_file or '无'}")
    log_message(logger, f"   示例文件: {len(few_shot_samples) if few_shot_samples else 0} 个示例")
    log_message(logger, f"   前言文件: {preface_file or '无'}")
    log_message(logger, f"   停止词: {stop or '无'}")
    log_message(logger, f"   日志目录: {log_dir}")
    log_message(logger, f"   输出文件: {zh_path}")
    log_message(logger, f"   {'='*50}")
    
    # 组装全文或分块：默认对"整个原文件文本（含YAML与正文）"进行一次性翻译
    chunks: List[str] = []
    if mode == "full":
        chunks = [raw_text]
    else:
        # 使用按行分割，确保整行不被截断
        chunks = split_text_by_lines(raw_text, chunk_size_chars, overlap_chars)
    terminology_txt: Optional[str] = None
    if terminology_file and terminology_file.exists():
        try:
            terminology_txt = terminology_file.read_text(encoding="utf-8")
        except Exception:
            terminology_txt = None
    start = time.time()
    outputs: List[str] = []
    prompts: List[str] = []
    # 直接对整份输入文本进行翻译（包含 YAML 与正文），不再分开处理标题/前言

    def chunkify_with_overlap_raw(text: str) -> List[str]:
        out_chunks: List[str] = []
        step_local = max(1, chunk_size_chars - max(0, overlap_chars))
        i = 0
        L = len(text)
        while i < L:
            j = min(L, i + chunk_size_chars)
            c = text[max(0, i - max(0, overlap_chars)): j]
            out_chunks.append(c)
            if j >= L:
                break
            i += step_local
        return out_chunks

    # 设置实时日志输出
    logger = None
    if realtime_log:
        # 提前定义log_path
        log_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d-%H%M%S")
        log_path = log_dir / f"translation_{path.stem}_{ts}.log"
        
        logger = setup_realtime_logging(log_path, stream_output=True)
        log_realtime(logger, f"开始处理文件: {path}")
        log_realtime(logger, f"模型: {model}, 模式: {mode}, 对照模式: {bilingual}")

    def run_chunks(active_chunks: List[str]) -> Tuple[List[str], List[str], bool, List[Dict[str, int]]]:
        outs: List[str] = []
        prms: List[str] = []
        metas: List[Dict[str, int]] = []
        log_message(logger, f"开始处理 {len(active_chunks)} 个块...")
        for i, ck in enumerate(active_chunks, 1):
            log_message(logger, f"处理第 {i}/{len(active_chunks)} 块，长度: {len(ck)}")
            out, prompt, ok, token_meta = translate_chunk_with_retry(
                ck, model, temperature, max_tokens, terminology_txt, stop, frequency_penalty, presence_penalty, retries, retry_wait, few_shot_samples, max_context_length, preface_file, bilingual, stream, logger, chunk_index=i
            )
            log_message(logger, f"第 {i} 块结果: ok={ok}, out_len={len(out)}, prompt_len={len(prompt)}")
            if not ok:
                log_message(logger, f"第 {i} 块翻译失败", "WARNING")
                # 即使失败，也保存结果用于调试
                if out.strip():
                    cleaned_out = clean_output_text(out)
                    if not cleaned_out.strip():
                        cleaned_out = out
                    outs.append(cleaned_out)
                    prms.append(prompt)
                metas.append(token_meta)
                return outs, prms, False, metas
            # 简单重复检测：若某块输出与上一块高度相似（前200字符相同），则截断
            if outs and out[:200] == outs[-1][:200]:
                out = out[: max(200, len(out)//2)]
            # 清理输出文本，去除思考部分
            log_message(logger, f"原始输出长度: {len(out)}")
            cleaned_out = clean_output_text(out)
            log_message(logger, f"清理后长度: {len(cleaned_out)}")
            if not cleaned_out.strip():
                log_message(logger, f"警告: 清理后输出为空，使用原始输出", "WARNING")
                cleaned_out = out
            outs.append(cleaned_out)
            prms.append(prompt)
            metas.append(token_meta)
        return outs, prms, True, metas

    # 首次尝试：按当前模式执行
    outs, prms, ok, metas = run_chunks(chunks)
    
    # 如果首次尝试失败，尝试分块重试
    if (not ok) and fallback_on_context and mode == "full":
        log_message(logger, f"首次翻译失败，尝试分块重试...")
        # 降级为对"原始全文"的字符重叠切分
        chunks2 = split_text_by_lines(raw_text, chunk_size_chars, overlap_chars)
        outs, prms, ok, metas = run_chunks(chunks2)
    
    # 即使检测到坏输出，也保存结果
    if outs:
        outputs.extend(outs)
        prompts.extend(prms)
        log_message(logger, f"保存了 {len(outs)} 个输出块")
    else:
        log_message(logger, f"警告: 没有有效的输出块", "WARNING")
    
    # 根据模式处理输出
    if bilingual:
        # 对照模式：直接使用模型输出的对照格式
        translation = "\n\n".join(outputs)
    else:
        # 单语模式：原有逻辑
        translation = "\n\n".join(outputs)
    
    # 质量检测：如果翻译不完整，尝试分块重试
    if fallback_on_context and mode == "full":
        log_message(logger, f"进行翻译质量检测...")
        if no_llm_check:
            is_good, reason = check_translation_quality_basic(raw_text, translation, bilingual)
        else:
            is_good, reason = check_translation_quality_with_llm(raw_text, translation, model, bilingual)
        
        if not is_good:
            log_message(logger, f"翻译质量检测失败: {reason}")
            log_message(logger, f"尝试分块重试...")
            # 使用更小的块大小进行分块重试
            chunk_size_for_fallback = min(8000, chunk_size_chars // 2)  # 使用更小的块大小
            chunks2 = split_text_by_lines(raw_text, chunk_size_for_fallback, overlap_chars)
            log_message(logger, f"分块重试: 使用 {len(chunks2)} 个块，每块最大 {chunk_size_for_fallback} 字符")
            outs2, prms2, ok2, metas2 = run_chunks(chunks2)
            if outs2:
                outputs = outs2
                prompts = prms2
                if bilingual:
                    translation = "\n\n".join(outputs)
                else:
                    translation = "\n\n".join(outputs)
                log_message(logger, f"分块重试完成，保存了 {len(outs2)} 个输出块")
            else:
                log_message(logger, f"分块重试也失败了", "WARNING")
        else:
            log_message(logger, f"翻译质量检测通过: {reason}")
    full_prompt = "\n\n".join(prompts)
    cost = time.time() - start

    zh_path.write_text(translation, encoding="utf-8")
    
    # 最终输出
    log_message(logger, f"WRITE {zh_path} ({cost:.1f}s)")


def expand_inputs(inputs: List[str]) -> List[Path]:
    files: List[Path] = []
    for p in inputs:
        pth = Path(p)
        if pth.is_dir():
            files.extend(sorted(pth.glob("*.txt")))
        else:
            # 支持通配符
            for m in glob.glob(p):
                mp = Path(m)
                if mp.is_file() and mp.suffix == ".txt":
                    files.append(mp)
    # 仅保留源文件（不含 _zh.txt）
    files = [f for f in files if not f.name.endswith("_zh.txt")]
    return files


def main() -> None:
    parser = argparse.ArgumentParser(description="批量翻译 Pixiv 小说到 _zh.txt")
    parser.add_argument("inputs", nargs="+", help="输入：文件/目录/通配符")
    parser.add_argument("--model", default="Qwen/Qwen3-32B-AWQ")
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--max-tokens", type=int, default=0, help="<=0 表示不限制（不传该参数）")
    parser.add_argument("--max-context-length", type=int, default=None, help="模型的最大上下文长度，如果不指定则根据模型名称自动推断")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--log-dir", default="logs")
    parser.add_argument("--terminology-file", type=Path, default=Path("tasks/translation/data/terminology.txt"))
    parser.add_argument("--chunk-size-chars", type=int, default=20000, help="分块模式下每次请求的最大字符数")
    parser.add_argument("--stop", nargs="*", default=["（未完待续）", "[END]"], help="生成停止词")
    parser.add_argument("--frequency-penalty", type=float, default=0.3)
    parser.add_argument("--presence-penalty", type=float, default=0.2, help="presence penalty 参数")
    parser.add_argument("--mode", choices=["full", "chunked"], default="full", help="全文一次性或分块模式")
    parser.add_argument("--overlap-chars", type=int, default=1000, help="分块模式下相邻块重叠字符数")
    parser.add_argument("--retries", type=int, default=3, help="每块最大重试次数")
    parser.add_argument("--retry-wait", type=float, default=2.0, help="重试前等待秒数")
    parser.add_argument("--fallback-on-context", action="store_true", help="上下文溢出时自动降级为分块")
    parser.add_argument("--limit", type=int, default=0, help="限制处理的文件数量，0表示不限制")
    parser.add_argument("--sample-file", type=Path, default=Path("tasks/translation/data/samples/sample.txt"), help="few-shot 示例文件")
    parser.add_argument("--preface-file", type=Path, default=Path("tasks/translation/data/preface.txt"), help="翻译指令模板文件")
    parser.add_argument("--bilingual", action="store_true", help="启用对照模式：输出日语原文+中文译文交错格式")
    parser.add_argument("--stream", action="store_true", help="启用流式输出，实时显示模型生成过程")
    parser.add_argument("--realtime-log", action="store_true", help="启用实时日志输出，同时显示在控制台和文件中")
    parser.add_argument("--no-llm-check", action="store_true", help="禁用大模型质量检测，使用基础检测")
    parser.add_argument("--strict-repetition-check", action="store_true", help="启用严格重复检测，更早发现并截断重复输出")
    args = parser.parse_args()

    files = expand_inputs(args.inputs)
    if not files:
        print("no files matched")
        sys.exit(1)

    # 限制处理文件数量
    if args.limit > 0:
        files = files[:args.limit]
        print(f"限制处理前 {args.limit} 个文件")

    # 加载 few-shot 示例
    few_shot_samples = load_few_shot_samples(args.sample_file)
    if few_shot_samples:
        print(f"加载了 {len(few_shot_samples)} 个 few-shot 示例")
        # 调试输出：打印完整的few-shot示例
        print("=" * 50)
        print("完整的 few-shot 示例:")
        print("=" * 50)
        for i, (input_text, output_text) in enumerate(few_shot_samples, 1):
            print(f"示例 {i}:")
            print("输入:")
            print(input_text)
            print("输出:")
            print(output_text)
            print("-" * 30)

    for f in files:
        process_file(
            f,
            model=args.model,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            overwrite=args.overwrite,
            log_dir=Path(args.log_dir),
            terminology_file=args.terminology_file,
            chunk_size_chars=args.chunk_size_chars,
            stop=args.stop,
            frequency_penalty=args.frequency_penalty,
            presence_penalty=args.presence_penalty,
            mode=args.mode,
            overlap_chars=args.overlap_chars,
            retries=args.retries,
            retry_wait=args.retry_wait,
            fallback_on_context=args.fallback_on_context,
            few_shot_samples=few_shot_samples,
            max_context_length=args.max_context_length,
            preface_file=str(args.preface_file),
            bilingual=args.bilingual,
            stream=args.stream,
            realtime_log=args.realtime_log,
            no_llm_check=args.no_llm_check,
        )


if __name__ == "__main__":
    main()


