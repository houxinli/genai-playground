#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import re
import yaml
from pathlib import Path
from typing import Dict, List, Tuple, Optional


def _normalize_whitespace(text: str) -> str:
    """规范化不可见空白与特殊空格，清除BOM与零宽字符，合并空格。"""
    if not text:
        return text
    # 移除 BOM 与零宽字符
    text = text.replace('\ufeff', '')  # BOM U+FEFF
    text = text.replace('\u200b', '')  # ZWSP U+200B
    text = text.replace('\u200c', '')  # ZWNJ U+200C
    text = text.replace('\u200d', '')  # ZWJ U+200D
    text = text.replace('\u2060', '')  # WORD JOINER
    # 将各种空格类字符替换为普通空格
    space_like = [
        '\u00a0',  # NBSP
        '\u2000', '\u2001', '\u2002', '\u2003', '\u2004', '\u2005',
        '\u2006', '\u2007', '\u2008', '\u2009', '\u200a', '\u202f',
        '\u205f', '\u3000'  # 全角空格
    ]
    for ch in space_like:
        text = text.replace(ch, ' ')
    # 合并多余空格并去首尾空格
    text = re.sub(r"[ \t\f\v]+", " ", text).strip()
    return text

def _clean_metadata_text(text: str) -> str:
    """清理元数据文本：去除<br/>标签与URL，并规范空白。"""
    if text is None:
        return ''
    # 去除各种形式的<br>标签
    text = re.sub(r"<\s*br\s*/?>", "", text, flags=re.IGNORECASE)
    # 去除任意HTML标签，如 <b>...</b>、<i> ... > 等
    text = re.sub(r"<[^>]+>", "", text)
    # 去除URL
    text = re.sub(r"https?://\S+", "", text)
    # 规范空白与不可见字符
    text = _normalize_whitespace(text)
    return text

def _transform_yaml_to_localized(chinese_yaml: str) -> List[str]:
    """将提取到的英文key元信息转换为中文本地化键名，并清理内容。
    目标键名顺序：ID, 标题, 简介, 系列(可选), 标签
    - novel_id -> ID
    - title -> 标题
    - caption -> 简介
    - series.title -> 系列（没有系列则不输出）
    - tags -> 标签
    """
    if not chinese_yaml.strip():
        return []

    lines = chinese_yaml.split('\n')
    id_value: Optional[str] = None
    title_value: Optional[str] = None
    caption_value: Optional[str] = None
    series_title_value: Optional[str] = None
    tags_value: Optional[str] = None

    i = 0
    while i < len(lines):
        line = lines[i]
        # 规范空白
        raw = line.rstrip('\n')
        if raw.startswith('novel_id:'):
            id_value = _clean_metadata_text(raw.split(':', 1)[1])
        elif raw.startswith('title:'):
            title_value = _clean_metadata_text(raw.split(':', 1)[1])
        elif raw.startswith('caption:'):
            caption_value = _clean_metadata_text(raw.split(':', 1)[1])
        elif raw.startswith('tags:'):
            tags_value = _clean_metadata_text(raw.split(':', 1)[1])
        elif raw.startswith('series:'):
            # 读取子字段 title
            j = i + 1
            while j < len(lines) and lines[j].startswith('  '):
                sub = lines[j].strip()
                if sub.startswith('title:'):
                    series_title_value = _clean_metadata_text(sub.split(':', 1)[1])
                    break
                j += 1
            # 跳过由外部逻辑控制递增，这里不改变 i
        i += 1

    localized: List[str] = []
    if id_value:
        localized.append(f"ID: {id_value}")
    if title_value:
        localized.append(f"标题: {title_value}")
    if caption_value:
        localized.append(f"简介: {caption_value}")
    if series_title_value:
        localized.append(f"系列: {series_title_value}")
    if tags_value:
        localized.append(f"标签: {tags_value}")
    return localized

def is_japanese_text(text: str) -> bool:
    """判断文本是否包含日文字符（平假名、片假名）"""
    if not text.strip():
        return False
    
    # 排除常见符号，只检测文字字符
    symbols_pattern = r'[「」『』（）【】\[\](){}「」『』、。，．！？；：\s\-\+\=\*\/\\\|\~\`\@\#\$\%\^\&\<\>♡❤︎]'
    text_without_symbols = re.sub(symbols_pattern, '', text)
    
    if not text_without_symbols.strip():
        return False
    
    # 检查是否包含日文假名
    hiragana_pattern = r'[\u3040-\u309f]'  # 平假名
    katakana_pattern = r'[\u30a0-\u30ff]'  # 片假名
    
    # 排除中黑点符号，因为它在中日文中都会使用
    has_hiragana = bool(re.search(hiragana_pattern, text_without_symbols))
    has_katakana = bool(re.search(katakana_pattern, text_without_symbols))
    
    # 如果只有中黑点符号，不算日文
    if has_katakana and not has_hiragana:
        # 检查是否只包含中黑点符号
        katakana_only_dot = re.sub(r'[\u30fb]', '', text_without_symbols)  # 移除中黑点
        if not re.search(katakana_pattern, katakana_only_dot):
            return False
    
    return has_hiragana or has_katakana


def is_chinese_text(text: str) -> bool:
    """判断文本是否主要是中文（排除日文）"""
    if not text.strip():
        return False
    
    # 排除常见符号，只检测文字字符
    symbols_pattern = r'[「」『』（）【】\[\](){}「」『』、。，．！？；：\s\-\+\=\*\/\\\|\~\`\@\#\$\%\^\&\<\>♡❤︎]'
    text_without_symbols = re.sub(symbols_pattern, '', text)
    
    if not text_without_symbols.strip():
        return False
    
    # 统计中文字符和日文字符的数量
    chinese_pattern = r'[\u4e00-\u9faf]'
    hiragana_pattern = r'[\u3040-\u309f]'
    katakana_pattern = r'[\u30a0-\u30ff]'
    
    chinese_count = len(re.findall(chinese_pattern, text_without_symbols))
    hiragana_count = len(re.findall(hiragana_pattern, text_without_symbols))
    # 排除中黑点符号计算片假名数量
    katakana_text = re.sub(r'[\u30fb]', '', text_without_symbols)
    katakana_count = len(re.findall(katakana_pattern, katakana_text))
    
    # 如果包含日文假名，需要进一步判断
    if hiragana_count > 0 or katakana_count > 0:
        # 如果中文字符数量明显多于日文字符，则认为是中文
        if chinese_count > (hiragana_count + katakana_count) * 2:
            return True
        else:
            return False
    
    # 如果没有日文假名，检查是否包含中文字符
    if chinese_count > 0:
        # 特殊处理：如果包含中黑点符号，需要进一步判断
        if re.search(r'[\u30fb]', text_without_symbols):
            # 移除中黑点后检查是否主要是中文字符
            text_without_dot = re.sub(r'[\u30fb]', '', text_without_symbols)
            remaining_chinese = len(re.findall(chinese_pattern, text_without_dot))
            total_chars = len(re.findall(r'[^\s]', text_without_dot))
            if total_chars > 0 and remaining_chinese / total_chars > 0.5:
                return True
        else:
            return True
    
    return False


def extract_title_from_yaml(yaml_content: str) -> str:
    """从YAML内容中提取中文标题"""
    try:
        lines = yaml_content.strip().split('\n')
        
        # 跳过开头的 ---
        if lines and lines[0].strip() == '---':
            lines = lines[1:]
        
        # 跳过结尾的 ---
        if lines and lines[-1].strip() == '---':
            lines = lines[:-1]
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # 处理title字段
            if line.startswith('title:'):
                # 检查下一行是否也是title
                if i + 1 < len(lines) and lines[i + 1].startswith('title:'):
                    # 返回第二个title（中文翻译）
                    title_text = lines[i + 1].replace('title:', '').strip()
                    title_text = _clean_metadata_text(title_text).strip()
                    # 若含标点，只取第一个标点前的部分
                    # 微信图书对标题行长度有限制, 建议不超过25字符
                    m = re.search(r"[，。、；：,.!?！？]", title_text)
                    if m:
                        title_text = title_text[:m.start()]
                    return title_text[:25]
                else:
                    # 只有一个title，检查是否包含中文
                    if is_chinese_text(line):
                        title_text = line.replace('title:', '').strip()
                        title_text = _clean_metadata_text(title_text).strip()
                        # 微信图书对标题行长度有限制, 建议不超过25字符
                        m = re.search(r"[，。、；：,.!?！？]", title_text)
                        if m:
                            title_text = title_text[:m.start()]
                        return title_text[:25]
                i += 1
            else:
                i += 1
        
        return "未知标题"
    
    except Exception as e:
        return "未知标题"


def extract_chinese_from_yaml(yaml_content: str) -> str:
    """从YAML内容中提取中文翻译部分"""
    try:
        # 由于YAML中有重复字段名，我们需要手动解析
        lines = yaml_content.strip().split('\n')
        
        # 跳过开头的 ---
        if lines and lines[0].strip() == '---':
            lines = lines[1:]
        
        # 跳过结尾的 ---
        if lines and lines[-1].strip() == '---':
            lines = lines[:-1]
        
        chinese_lines = []
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # 处理novel_id字段
            if line.startswith('novel_id:'):
                chinese_lines.append(line)
                i += 1
                continue
            
            # 处理title字段，保留完整中文标题
            if line.startswith('title:'):
                # 如果下一行也是title，保留第二个（中文翻译）
                if i + 1 < len(lines) and lines[i + 1].startswith('title:'):
                    full_title = lines[i + 1].split(':', 1)[1]
                    full_title = _clean_metadata_text(full_title).strip()
                    chinese_lines.append(f"title: {full_title}")
                    i += 2
                else:
                    # 单一title且包含中文时保留
                    if is_chinese_text(line):
                        full_title = line.split(':', 1)[1]
                        full_title = _clean_metadata_text(full_title).strip()
                        chinese_lines.append(f"title: {full_title}")
                    i += 1
                continue
            
            elif line.startswith('caption:'):
                # 检查下一行是否也是caption
                if i + 1 < len(lines) and lines[i + 1].startswith('caption:'):
                    # 保留第二个caption（中文翻译），并清理
                    cap_text = lines[i + 1].split(':', 1)[1]
                    cap_text = _clean_metadata_text(cap_text).strip()
                    chinese_lines.append(f"caption: {cap_text}")
                    i += 2
                else:
                    # 只有一个caption，检查是否包含中文
                    if is_chinese_text(line):
                        cap_text = line.split(':', 1)[1]
                        cap_text = _clean_metadata_text(cap_text).strip()
                        chinese_lines.append(f"caption: {cap_text}")
                    i += 1
                continue
            
            elif line.startswith('tags:'):
                # 检查下一行是否也是tags
                if i + 1 < len(lines) and lines[i + 1].startswith('tags:'):
                    # 保留第二个tags（中文翻译）
                    chinese_lines.append(lines[i + 1])
                    i += 2
                else:
                    # 只有一个tags，检查是否包含中文
                    if is_chinese_text(line):
                        chinese_lines.append(line)
                    i += 1
                continue
            
            elif line.startswith('series:'):
                chinese_lines.append(line)
                i += 1
                # 处理series的子字段
                while i < len(lines) and lines[i].startswith('  '):
                    sub_line = lines[i]
                    # 只处理title字段
                    if sub_line.strip().startswith('title:'):
                        # 检查下一行是否也是title
                        if i + 1 < len(lines) and lines[i + 1].strip().startswith('title:'):
                            # 保留第二个title（中文翻译）
                            chinese_lines.append(lines[i + 1])
                            i += 2
                        else:
                            # 只有一个title，检查是否包含中文或为空
                            if is_chinese_text(sub_line) or sub_line.strip() == 'title:':
                                chinese_lines.append(sub_line)
                            i += 1
                    else:
                        # 跳过其他字段（id, order等）
                        i += 1
                continue
            
            else:
                # 跳过所有其他字段
                i += 1
                continue
        
        return '\n'.join(chinese_lines)
    
    except Exception as e:
        raise ValueError(f"YAML解析失败: {e}")


def extract_chinese_from_content(content_lines: List[str], include_original: bool = False) -> List[str]:
    """从正文内容中提取中文译文行"""
    result = []
    i = 0
    
    while i < len(content_lines):
        line = content_lines[i]
        
        # 空行直接保留
        if not line.strip():
            result.append(line)
            i += 1
            continue
        
        # 检查是否是日文行（优先判断为日文）
        if is_japanese_text(line):
            # 检查下一行是否是中文翻译
            if i + 1 < len(content_lines):
                next_line = content_lines[i + 1]
                if is_chinese_text(next_line):
                    # 找到翻译
                    if include_original:
                        # 双语模式：保留原文行和中文行
                        result.append(line)
                        result.append(next_line)
                    else:
                        # 纯中文模式：只保留中文行
                        result.append(next_line)
                    i += 2  # 跳过日文行和中文行
                    continue
                elif next_line.strip() == line.strip():
                    # 如果下一行与当前行完全相同（如 B:111, ◇），只保留一次
                    result.append(line)
                    i += 2  # 跳过重复行
                    continue
                elif not is_japanese_text(next_line) and not is_chinese_text(next_line) and next_line.strip():
                    # 下一行既不是日文也不是中文，但非空，可能是符号翻译
                    result.append(next_line)
                    i += 2  # 跳过日文行和符号行
                    continue
                else:
                    # 没有找到翻译，保留日文行并标记
                    result.append(line.rstrip() + " [日]")
                    i += 1
                    continue
            else:
                # 最后一行是日文，标记翻译缺失
                result.append(line.rstrip() + " [日]")
                i += 1
                continue
        
        # 检查是否是中文行
        elif is_chinese_text(line):
            # 如果中文行中包含假名，标记为[中]
            if is_japanese_text(line):
                result.append(line.rstrip() + " [中]")
            else:
                result.append(line)
            i += 1
            continue
        
        # 其他情况：保留原行（可能是数字、符号等）
        else:
            # 检查下一行是否与当前行完全相同
            if i + 1 < len(content_lines):
                next_line = content_lines[i + 1]
                if next_line.strip() == line.strip():
                    # 如果下一行与当前行完全相同（如 B:111, ◇），只保留一次
                    result.append(line)
                    i += 2  # 跳过重复行
                    continue
            
            # 其他情况，保留原行
            result.append(line)
            i += 1
            continue
    
    # 压缩文章内部的空行，最多保留2个连续空行
    compressed_lines = []
    empty_count = 0
    
    for line in result:
        if not line.strip():
            empty_count += 1
            if empty_count <= 2:
                compressed_lines.append(line)
        else:
            empty_count = 0
            compressed_lines.append(line)
    
    return compressed_lines


def process_bilingual_file(input_path: Path, output_path: Path, include_original: bool = False) -> bool:
    """处理单个双语文件"""
    try:
        # 读取文件内容
        content = input_path.read_text(encoding='utf-8', errors='ignore')
        lines = content.split('\n')
        
        # 找到YAML分隔符
        yaml_end_line = -1
        found_first_separator = False
        for i, line in enumerate(lines):
            if line.strip() == '---':
                if found_first_separator:
                    yaml_end_line = i
                    break
                else:
                    found_first_separator = True
        
        if yaml_end_line == -1:
            raise ValueError("未找到YAML分隔符")
        
        # 提取YAML部分
        yaml_lines = lines[:yaml_end_line + 1]
        yaml_content = '\n'.join(yaml_lines)
        
        # 提取正文部分
        content_lines = lines[yaml_end_line + 1:]
        
        # 处理YAML
        chinese_yaml = extract_chinese_from_yaml(yaml_content)
        
        # 处理正文
        chinese_content = extract_chinese_from_content(content_lines, include_original)
        
        # 合并结果
        result_lines = []
        if chinese_yaml.strip():
            result_lines.append('---')  # YAML部分前的分割线
            result_lines.extend(chinese_yaml.split('\n'))
            result_lines.append('')  # YAML部分后的第一个空行
            result_lines.append('')  # YAML部分后的第二个空行
        result_lines.extend(chinese_content)
        
        # 确保输出目录存在
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 写入文件
        output_path.write_text('\n'.join(result_lines), encoding='utf-8')
        
        return True
    
    except Exception as e:
        print(f"处理文件失败 {input_path}: {e}")
        return False


def extract_novel_id_from_yaml(yaml_content: str) -> Optional[int]:
    """从YAML内容中提取 novel_id（数字）。失败返回 None。"""
    try:
        lines = yaml_content.strip().split('\n')
        # 跳过开头/结尾分隔
        if lines and lines[0].strip() == '---':
            lines = lines[1:]
        if lines and lines[-1].strip() == '---':
            lines = lines[:-1]
        for line in lines:
            if line.startswith('novel_id:'):
                raw = line.split(':', 1)[1].strip()
                # 只保留数字前缀
                m = re.match(r"(\d+)", raw)
                if m:
                    return int(m.group(1))
        return None
    except Exception:
        return None


def merge_chinese_files(input_dir: Path, include_original: bool = False) -> bool:
    """合并文件夹中所有双语文件的中文部分到一个文件，按 novel_id 升序排序。"""
    try:
        candidate_files = list(input_dir.rglob("*.txt"))
        if not candidate_files:
            print(f"在目录 {input_dir} 中未找到双语文件")
            return False

        # 先预读每个文件，解析 YAML 与 novel_id，用于排序
        file_infos: List[Tuple[int, Path, List[str], str]] = []
        failed_count = 0
        for file_path in candidate_files:
            try:
                content = file_path.read_text(encoding='utf-8', errors='ignore')
                lines = content.split('\n')
                # 找第二个 '---'
                yaml_end_line = -1
                found_first_separator = False
                for i, line in enumerate(lines):
                    if line.strip() == '---':
                        if found_first_separator:
                            yaml_end_line = i
                            break
                        found_first_separator = True
                if yaml_end_line == -1:
                    # 跳过无YAML结构的文件
                    print(f"跳过文件 {file_path}: 未找到YAML分隔符")
                    failed_count += 1
                    continue
                yaml_lines = lines[:yaml_end_line + 1]
                yaml_content = '\n'.join(yaml_lines)
                content_lines = lines[yaml_end_line + 1:]
                novel_id = extract_novel_id_from_yaml(yaml_content)
                if novel_id is None:
                    # 将无法识别的 novel_id 放在末尾（使用一个大值）
                    novel_id = 10**18
                file_infos.append((novel_id, file_path, content_lines, yaml_content))
            except Exception as e:
                print(f"预读失败 {file_path}: {e}")
                failed_count += 1

        # 按 novel_id 升序排序；若 novel_id 相同则按文件名作为次序键
        file_infos.sort(key=lambda t: (t[0], t[1].name))

        merged_content: List[str] = []
        processed_count = 0
        chapter_count = 0

        for novel_id, file_path, content_lines, yaml_content in file_infos:
            try:
                # 标题与YAML中文提取
                title = extract_title_from_yaml(yaml_content)
                chinese_yaml = extract_chinese_from_yaml(yaml_content)
                chinese_content = extract_chinese_from_content(content_lines, include_original)

                # 章节标题：第X章 标题（数字无空格；标题最多15字，遇首标点截断，规范空白）
                chapter_count += 1
                safe_title = _normalize_whitespace(title)
                # 微信图书对标题行长度有限制, 建议不超过25字符
                m = re.search(r"[，。、；：,.!?！？]", safe_title)
                if m:
                    safe_title = safe_title[:m.start()]
                merged_content.append(f"第{chapter_count}章 {safe_title[:25]}")
                merged_content.append("")

                # YAML（含 novel_id），转换为本地化键名并清理
                if chinese_yaml.strip():
                    localized_yaml = _transform_yaml_to_localized(chinese_yaml)
                    merged_content.extend(localized_yaml)
                    merged_content.append("")
                    merged_content.append("")

                # 正文
                merged_content.extend(chinese_content)

                # 文章之间增加 10 行空行（无分割线）
                merged_content.extend([""] * 10)

                processed_count += 1
                print(f"已处理: {file_path}")
            except Exception as e:
                print(f"处理文件失败 {file_path}: {e}")
                failed_count += 1

        # 输出文件
        suffix = "_bilingual.txt" if include_original else "_zh.txt"
        output_file = input_dir.parent / f"{input_dir.name}{suffix}"
        output_file.write_text('\n'.join(merged_content), encoding='utf-8')

        print(f"\n合并完成: 成功={processed_count}, 失败={failed_count}")
        print(f"合并文件: {output_file}")
        return True
    except Exception as e:
        print(f"合并失败: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="从双语文件中提取中文部分")
    parser.add_argument("input", type=str, help="输入文件或目录路径")
    parser.add_argument("--debug", action="store_true", help="debug模式：输出文件与原文件在同一文件夹，文件名加_zh后缀")
    parser.add_argument("--output", type=str, help="输出目录路径（非debug模式时使用）")
    parser.add_argument("--merge", action="store_true", help="合并模式：将文件夹中所有文件的中文部分合并到一个文件")
    parser.add_argument("--bilingual", action="store_true", help="双语模式：正文保留原文行与中文译文行")
    
    args = parser.parse_args()
    
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"输入路径不存在: {input_path}")
        return
    
    processed_count = 0
    failed_count = 0
    
    if input_path.is_file():
        # 处理单个文件
        if args.debug:
            # debug模式：在同一文件夹，依据模式选择后缀
            suffix = "_bilingual" if args.bilingual else "_zh"
            output_path = input_path.parent / f"{input_path.stem}{suffix}{input_path.suffix}"
        else:
            # 非debug模式：在平行文件夹
            if args.output:
                output_dir = Path(args.output)
            else:
                # 自动生成输出目录名
                if '_bilingual' in str(input_path.parent):
                    output_dir = input_path.parent.parent / input_path.parent.name.replace('_bilingual', '_zh')
                else:
                    output_dir = input_path.parent / f"{input_path.parent.name}_zh"
            
            output_path = output_dir / input_path.name
        
        if process_bilingual_file(input_path, output_path, include_original=args.bilingual):
            print(f"成功处理: {input_path} -> {output_path}")
            processed_count += 1
        else:
            failed_count += 1
    
    else:
        # 处理目录
        if args.merge:
            # 合并模式
            merge_chinese_files(input_path, include_original=args.bilingual)
        else:
            # 普通模式：处理目录中的每个文件
            bilingual_files = list(input_path.rglob("*_bilingual.txt"))
            
            for file_path in bilingual_files:
                if args.debug:
                    # debug模式：在同一文件夹，文件名加_zh后缀
                    output_path = file_path.parent / f"{file_path.stem}_zh{file_path.suffix}"
                else:
                    # 非debug模式：在平行文件夹
                    if args.output:
                        output_dir = Path(args.output)
                    else:
                        # 自动生成输出目录名
                        if '_bilingual' in str(file_path.parent):
                            output_dir = file_path.parent.parent / file_path.parent.name.replace('_bilingual', '_zh')
                        else:
                            output_dir = file_path.parent / f"{file_path.parent.name}_zh"
                    
                    output_path = output_dir / file_path.name
                
                if process_bilingual_file(file_path, output_path, include_original):
                    print(f"成功处理: {file_path} -> {output_path}")
                    processed_count += 1
                else:
                    failed_count += 1
            
            print(f"\n处理完成: 成功={processed_count}, 失败={failed_count}")


if __name__ == "__main__":
    main()
