"""
翻译工具函数模块
"""
import re
import time
from pathlib import Path
from typing import List, Tuple, Optional, Dict


def clean_output_text(text: str) -> str:
    """清理输出文本，去除思考部分等"""
    if not text or not text.strip():
        return text
    
    # 移除思考部分
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    text = re.sub(r'（思考：.*?）', '', text, flags=re.DOTALL)
    text = re.sub(r'（注：.*?）', '', text, flags=re.DOTALL)
    
    # 清理多余空行
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        if line.strip():
            cleaned_lines.append(line)
        elif cleaned_lines and cleaned_lines[-1].strip():
            cleaned_lines.append(line)
    
    result = '\n'.join(cleaned_lines).strip()
    return result if result else text


def split_text_by_lines(text: str, max_chars: int, overlap_chars: int) -> List[str]:
    """按行分割文本，确保整行不被截断"""
    lines = text.split('\n')
    chunks = []
    current_chunk = []
    current_length = 0
    
    for line in lines:
        line_length = len(line) + 1  # +1 for newline
        if current_length + line_length > max_chars and current_chunk:
            chunk_text = '\n'.join(current_chunk)
            chunks.append(chunk_text)
            
            if overlap_chars > 0 and len(chunk_text) > overlap_chars:
                overlap_text = chunk_text[-overlap_chars:]
                last_newline = overlap_text.rfind('\n')
                if last_newline > 0:
                    overlap_text = overlap_text[last_newline + 1:]
                current_chunk = [overlap_text] if overlap_text else []
                current_length = len(overlap_text)
            else:
                current_chunk = []
                current_length = 0
        
        current_chunk.append(line)
        current_length += line_length
    
    if current_chunk:
        chunks.append('\n'.join(current_chunk))
    
    return chunks


def parse_yaml_meta(yaml_text: str) -> Dict[str, str]:
    """解析YAML格式的元数据"""
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
    """按段落分割文本"""
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


def looks_bad_output(text: str, original_text: str = "") -> bool:
    """检查输出是否质量不佳"""
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
        print(f"    looks_bad_output: 检测到标点符号缺失")
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


def expand_inputs(inputs: List[str]) -> List[Path]:
    """展开输入文件列表，支持通配符和目录"""
    import glob
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
    return [f for f in files if not f.name.endswith("_zh.txt")]


def get_log_filename() -> str:
    """生成日志文件名"""
    return f"translation_{time.strftime('%Y%m%d-%H%M%S')}.log"
