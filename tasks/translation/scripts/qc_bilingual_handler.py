#!/usr/bin/env python3
"""
Bilingual文件QC处理脚本
参考bilingual-simple模式的处理方式，对bilingual文件进行QC并生成标注版本
"""

import sys
import re
from pathlib import Path
from datetime import datetime
from typing import List, Tuple, Dict, Optional

# 添加src到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.quality_checker import QualityChecker
from src.core.config import TranslationConfig
from src.core.logger import UnifiedLogger
from src.utils.format import create_bilingual_output

class BilingualQCHandler:
    """Bilingual文件QC处理器"""
    
    def __init__(self, config: TranslationConfig, logger: Optional[UnifiedLogger] = None):
        self.config = config
        self.logger = logger or UnifiedLogger(None, config)
        self.qc = QualityChecker(config, logger)
    
    def parse_bilingual_file(self, file_path: str) -> Tuple[List[str], List[str], Dict]:
        """
        解析bilingual文件，提取原文、译文和YAML数据
        
        Returns:
            (original_lines, translated_lines, yaml_data)
        """
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        lines = content.splitlines(keepends=True)
        original_lines = []
        translated_lines = []
        yaml_data = {}
        
        # 处理YAML部分
        yaml_end_idx = -1
        if lines and lines[0].strip() == '---':
            yaml_lines = []
            for i, line in enumerate(lines[1:], 1):
                if line.strip() == '---':
                    yaml_end_idx = i
                    break
                yaml_lines.append(line)
            
            # 解析YAML数据
            yaml_content = ''.join(yaml_lines)
            yaml_data = self._parse_yaml_content(yaml_content)
        
        # 处理正文部分
        start_idx = yaml_end_idx + 1 if yaml_end_idx >= 0 else 0
        body_lines = lines[start_idx:]
        
        # 解析bilingual格式
        i = 0
        while i < len(body_lines):
            line = body_lines[i]
            
            # 检查下一行是否是译文
            if i + 1 < len(body_lines):
                next_line = body_lines[i + 1]
                
                # 判断是否为对照行
                is_pair = self._is_translation_pair(line, next_line)
                
                if is_pair:
                    original_lines.append(line.rstrip())
                    translated_lines.append(next_line.rstrip())
                    i += 2
                else:
                    original_lines.append(line.rstrip())
                    translated_lines.append('')
                    i += 1
            else:
                original_lines.append(line.rstrip())
                translated_lines.append('')
                i += 1
        
        return original_lines, translated_lines, yaml_data
    
    def _parse_yaml_content(self, yaml_content: str) -> Dict:
        """解析YAML内容"""
        yaml_data = {}
        for line in yaml_content.split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                yaml_data[key.strip()] = value.strip()
        return yaml_data
    
    def _is_translation_pair(self, line1: str, line2: str) -> bool:
        """判断两行是否为翻译对照"""
        # YAML字段对照
        if (line1.startswith('title:') and line2.startswith('title:') and line1 != line2) or \
           (line1.startswith('caption:') and line2.startswith('caption:') and line1 != line2) or \
           (line1.startswith('tags:') and line2.startswith('tags:') and line1 != line2):
            return True
        
        # 对话对照
        if line1.startswith('「') and line2.startswith('「') and line1 != line2:
            return True
        
        # 正文对照
        if line1.startswith('　') and line2.startswith('　') and line1 != line2:
            return True
        
        return False
    
    def perform_qc(self, original_lines: List[str], translated_lines: List[str]) -> Tuple[List[str], str, str]:
        """
        执行QC检查
        
        Returns:
            (verdicts, summary, conclusion)
        """
        # 过滤空白行进行QC
        non_empty_pairs = []
        for orig, trans in zip(original_lines, translated_lines):
            if orig.strip() or trans.strip():
                non_empty_pairs.append((orig, trans))
        
        if not non_empty_pairs:
            return [], "无有效内容进行QC", "通过"
        
        # 准备QC输入
        orig_text = '\n'.join([pair[0] for pair in non_empty_pairs])
        trans_text = '\n'.join([pair[1] for pair in non_empty_pairs])
        
        # 执行逐行规则QC
        verdicts, summary, conclusion = self.qc.check_translation_quality_rules_lines(
            orig_text, trans_text, bilingual=True
        )
        
        return verdicts, summary, conclusion
    
    def create_qc_annotated_output(self, original_lines: List[str], translated_lines: List[str], 
                                 verdicts: List[str], yaml_data: Dict) -> str:
        """
        创建QC标注的输出文件
        """
        result_lines = []
        
        # 添加YAML部分
        if yaml_data:
            result_lines.append('---')
            for key, value in yaml_data.items():
                result_lines.append(f'{key}: {value}')
            result_lines.append('---')
            result_lines.append('')
        
        # 处理正文部分
        non_empty_pairs = []
        for orig, trans in zip(original_lines, translated_lines):
            if orig.strip() or trans.strip():
                non_empty_pairs.append((orig, trans))
        
        # 创建标注的bilingual输出
        annotated_orig_lines = []
        annotated_trans_lines = []
        
        verdict_idx = 0
        for i, (orig, trans) in enumerate(zip(original_lines, translated_lines)):
            annotated_orig_lines.append(orig)
            
            if orig.strip() or trans.strip():
                # 这是有内容的行
                if verdict_idx < len(verdicts):
                    verdict = verdicts[verdict_idx]
                    if verdict == 'BAD':
                        # 添加QC标注
                        annotated_trans_lines.append(f"{trans} [QC: BAD]")
                    else:
                        annotated_trans_lines.append(trans)
                    verdict_idx += 1
                else:
                    annotated_trans_lines.append(trans)
            else:
                # 空白行
                annotated_trans_lines.append(trans)
        
        # 使用统一的bilingual输出格式
        bilingual_result = create_bilingual_output(annotated_orig_lines, annotated_trans_lines)
        result_lines.append(bilingual_result)
        
        return '\n'.join(result_lines)
    
    def get_output_path(self, input_path: Path) -> Path:
        """获取输出文件路径，参考bilingual-simple模式"""
        stem = input_path.stem
        
        # 移除原有的_bilingual后缀（如果存在）
        if stem.endswith('_bilingual'):
            stem = stem[:-10]  # 移除'_bilingual'
        
        if self.config.debug:
            # debug模式：在原目录生成_qc_bilingual文件
            ts = datetime.now().strftime('%Y%m%d-%H%M%S')
            return input_path.parent / f"{stem}_{ts}_qc_bilingual.txt"
        else:
            # 非debug模式：创建qc_bilingual子目录
            output_dir = input_path.parent.parent / f"{input_path.parent.name}_qc_bilingual"
            output_dir.mkdir(parents=True, exist_ok=True)
            return output_dir / f"{stem}_qc_bilingual.txt"
    
    def process_file(self, input_path: str) -> bool:
        """处理单个bilingual文件"""
        input_file = Path(input_path)
        if not input_file.exists():
            self.logger.error(f"输入文件不存在: {input_file}")
            return False
        
        self.logger.info(f"开始处理bilingual文件: {input_file}")
        
        try:
            # 解析文件
            original_lines, translated_lines, yaml_data = self.parse_bilingual_file(input_path)
            self.logger.info(f"解析完成: 原文{len(original_lines)}行, 译文{len(translated_lines)}行")
            
            # 执行QC
            verdicts, summary, conclusion = self.perform_qc(original_lines, translated_lines)
            self.logger.info(f"QC完成: {summary}")
            
            # 创建标注输出
            annotated_content = self.create_qc_annotated_output(
                original_lines, translated_lines, verdicts, yaml_data
            )
            
            # 保存结果
            output_path = self.get_output_path(input_file)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(annotated_content)
            
            self.logger.info(f"QC标注文件已保存: {output_path}")
            
            # 输出QC统计信息
            good_count = verdicts.count('GOOD')
            bad_count = verdicts.count('BAD')
            total_count = len(verdicts)
            pass_rate = good_count / total_count * 100 if total_count > 0 else 0
            
            print(f"\n=== QC统计 ===")
            print(f"总行数: {total_count}")
            print(f"GOOD: {good_count}")
            print(f"BAD: {bad_count}")
            print(f"通过率: {pass_rate:.1f}%")
            print(f"结论: {conclusion}")
            print(f"输出文件: {output_path}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"处理文件时出错: {e}")
            return False

def main():
    if len(sys.argv) != 2:
        print("用法: python qc_bilingual_handler.py <bilingual_file>")
        sys.exit(1)
    
    input_path = sys.argv[1]
    
    # 初始化配置
    config = TranslationConfig()
    config.bilingual_simple = True  # 使用bilingual模式
    config.debug = True  # 默认debug模式，可以修改
    
    # 创建日志器（简化模式）
    logger = UnifiedLogger(None, config)
    
    # 创建处理器
    handler = BilingualQCHandler(config, logger)
    
    # 处理文件
    success = handler.process_file(input_path)
    
    if success:
        print("QC处理完成！")
    else:
        print("QC处理失败！")
        sys.exit(1)

if __name__ == "__main__":
    main()
