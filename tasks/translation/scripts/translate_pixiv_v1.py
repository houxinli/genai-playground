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
from pathlib import Path
from typing import List, Tuple, Optional, Dict

from openai import OpenAI
from openai import BadRequestError


def clean_output_text(text: str) -> str:
    """清理输出文本，去除思考部分等"""
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
                    while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith('input:'):
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


def translate_with_local_llm(text: str, model: str, temperature: float, max_tokens: int, terminology: Optional[str] = None, stop: Optional[List[str]] = None, frequency_penalty: Optional[float] = None, presence_penalty: Optional[float] = None, few_shot_samples: Optional[List[Tuple[str, str]]] = None, max_context_length: Optional[int] = None, preface_file: Optional[str] = None) -> Tuple[str, str, Dict[str, int]]:
    # 组装带术语表的提示词
    if preface_file and Path(preface_file).exists():
        with open(preface_file, 'r', encoding='utf-8') as f:
            preface = f.read().strip() + "\n"
    else:
        # 默认preface
        preface = (
            "请将以下日语文本忠实翻译为中文：\n"
            "- 严格保持原文的分段与分行，不合并、不省略、不添加解释；\n"
            "- 对话与引号样式对齐，空行位置保持不变；\n"
            "- 仅输出译文本身，不要额外说明或思考内容。\n"
        )
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
    print(f"    调用模型，prompt长度: {len(prompt)}")
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
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=chosen_max_tokens,
            **kwargs,
        )
        result = resp.choices[0].message.content.strip()
        print(f"    模型返回，结果长度: {len(result)}")
        return result, prompt, token_meta
    except Exception as e:
        print(f"    模型调用失败: {e}")
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
    
    # 2. 检测单字符过长重复（超过15次，之前是8次）
    for ch in set(tail):
        if ch * 15 in tail:  # 从8次改为15次
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
) -> Tuple[str, str, bool, Dict[str, int]]:
    """返回 (output, prompt, ok)。ok=False 表示建议降级分块/或重试失败。"""
    last_err = None
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
            )
            if looks_bad_output(out, chunk_text):
                print(f"    检测到坏输出，但仍保存结果")
                # 即使检测到坏输出，也返回成功，让上层函数保存结果
                return out, prompt, True, token_meta
            return out, prompt, True, token_meta
        except BadRequestError as e:  # 例如上下文溢出
            last_err = e
            msg = str(e).lower()
            if any(k in msg for k in ["context", "too many tokens", "maximum context length", "max_tokens must be"]):
                # 上下文相关错误，提示外层降级为分段
                return "", "", False, {}
            time.sleep(retry_wait)
            continue
        except Exception as e:
            last_err = e
            time.sleep(retry_wait)
            continue
    # 多次失败
    return "", "", False, {}


def process_file(path: Path, model: str, temperature: float, max_tokens: int, overwrite: bool, log_dir: Path, terminology_file: Optional[Path], chunk_size_chars: int, stop: Optional[List[str]], frequency_penalty: Optional[float], presence_penalty: Optional[float], mode: str, overlap_chars: int, retries: int, retry_wait: float, fallback_on_context: bool, few_shot_samples: Optional[List[Tuple[str, str]]], max_context_length: Optional[int] = None, preface_file: Optional[str] = None) -> None:
    zh_path = path.with_name(path.stem + "_zh.txt")
    if zh_path.exists() and not overwrite:
        print(f"SKIP {zh_path} (exists)")
        return
    raw_text = path.read_text(encoding="utf-8", errors="ignore")
    if not raw_text.strip():
        print(f"WARN empty file: {path}")
        return
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

    def run_chunks(active_chunks: List[str]) -> Tuple[List[str], List[str], bool, List[Dict[str, int]]]:
        outs: List[str] = []
        prms: List[str] = []
        metas: List[Dict[str, int]] = []
        print(f"  开始处理 {len(active_chunks)} 个块...")
        for i, ck in enumerate(active_chunks, 1):
            print(f"  处理第 {i}/{len(active_chunks)} 块，长度: {len(ck)}")
            out, prompt, ok, token_meta = translate_chunk_with_retry(
                ck, model, temperature, max_tokens, terminology_txt, stop, frequency_penalty, presence_penalty, retries, retry_wait, few_shot_samples, max_context_length, preface_file
            )
            print(f"  第 {i} 块结果: ok={ok}, out_len={len(out)}, prompt_len={len(prompt)}")
            if not ok:
                print(f"  第 {i} 块翻译失败")
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
            print(f"  原始输出长度: {len(out)}")
            cleaned_out = clean_output_text(out)
            print(f"  清理后长度: {len(cleaned_out)}")
            if not cleaned_out.strip():
                print(f"  警告: 清理后输出为空，使用原始输出")
                cleaned_out = out
            outs.append(cleaned_out)
            prms.append(prompt)
            metas.append(token_meta)
        return outs, prms, True, metas

    # 首次尝试：按当前模式执行
    outs, prms, ok, metas = run_chunks(chunks)
    if (not ok) and fallback_on_context and mode == "full":
        # 降级为对"原始全文"的字符重叠切分
        chunks2 = split_text_by_lines(raw_text, chunk_size_chars, overlap_chars)
        outs, prms, ok, metas = run_chunks(chunks2)
    # 即使检测到坏输出，也保存结果
    if outs:
        outputs.extend(outs)
        prompts.extend(prms)
        print(f"  保存了 {len(outs)} 个输出块")
    else:
        print(f"  警告: 没有有效的输出块")
    translation = "\n\n".join(outputs)
    full_prompt = "\n\n".join(prompts)
    cost = time.time() - start

    zh_path.write_text(translation, encoding="utf-8")
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    # 日志文件名包含输入文件名，便于定位
    log_path = log_dir / f"translation_{path.stem}_{ts}.log"
    
    # 显示log文件名
    print(f"日志文件: {log_path}")
    
    # 优化日志记录：去重prompt中的重复部分
    def deduplicate_prompts(prompts: List[str]) -> str:
        """去重prompt中的重复部分，特别是few-shot示例"""
        # 当只有一个块时，仍需包含翻译结果，避免日志只有prompt没有结果
        if len(prompts) <= 1:
            single_prompt = prompts[0] if prompts else ""
            single_output = outputs[0] if outputs else ""
            return f"{single_prompt}\n\n翻译结果:\n{single_output}\n"
        
        # 提取第一个prompt作为模板
        template_prompt = prompts[0]
        
        # 分离模板中的固定部分（preface + few-shot）和变化部分（原文）
        lines = template_prompt.split('\n')
        fixed_part = []
        variable_part = []
        in_variable = False
        
        for line in lines:
            if line.strip() == "原文：":
                in_variable = True
                fixed_part.append(line)
            elif in_variable:
                variable_part.append(line)
            else:
                fixed_part.append(line)
        
        fixed_text = '\n'.join(fixed_part)
        
        # 构建去重后的日志
        deduplicated_log = f"固定部分（preface + few-shot）:\n{'-' * 50}\n{fixed_text}\n{'-' * 50}\n\n"
        
        # 添加每次翻译的原文和结果
        for i, (prompt, output) in enumerate(zip(prompts, outputs), 1):
            # 提取原文部分
            prompt_lines = prompt.split('\n')
            prompt_variable_part = []
            in_prompt_variable = False
            
            for line in prompt_lines:
                if line.strip() == "原文：":
                    in_prompt_variable = True
                    prompt_variable_part.append(line)
                elif in_prompt_variable and line.strip() == "翻译结果：":
                    break
                elif in_prompt_variable:
                    prompt_variable_part.append(line)
            
            prompt_variable_text = '\n'.join(prompt_variable_part)
            
            deduplicated_log += f"第 {i} 次翻译:\n{'-' * 30}\n"
            deduplicated_log += f"原文:\n{prompt_variable_text}\n\n"
            deduplicated_log += f"翻译结果:\n{output}\n\n"
        
        return deduplicated_log
    
    # 生成去重后的日志内容
    deduplicated_content = deduplicate_prompts(prompts)
    
    with log_path.open("w", encoding="utf-8") as f:
        f.write(f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"模型: {model}\n")
        f.write(f"输入文件: {path}\n")
        f.write(f"输出文件: {zh_path}\n")
        f.write(f"耗时: {cost:.1f}s\n")
        f.write(f"模式: {mode}\n")
        f.write(f"块数: {len(chunks)}\n")
        # 写入 tokens 估计
        if 'metas' in locals() and metas:
            if len(metas) == 1:
                m = metas[0] or {}
                f.write(f"估算输入tokens: {m.get('estimated_input_tokens', 0)}\n")
                f.write(f"预计输出上限tokens(含思考+译文): {m.get('estimated_output_tokens', 0)}\n")
                f.write(f"max_context_length: {m.get('max_context_length', 0)}\n")
                f.write(f"used_max_tokens: {m.get('used_max_tokens', 0)}\n")
            else:
                for idx, m in enumerate(metas, 1):
                    m = m or {}
                    f.write(f"[块{idx}] 估算输入tokens: {m.get('estimated_input_tokens', 0)}, 预计输出上限: {m.get('estimated_output_tokens', 0)}, used_max_tokens: {m.get('used_max_tokens', 0)}\n")
        f.write("=" * 50 + "\n")
        f.write(deduplicated_content)

    print(f"WRITE {zh_path} ({cost:.1f}s)")


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
    parser.add_argument("--log-dir", default="tasks/translation/logs")
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
        )


if __name__ == "__main__":
    main()


