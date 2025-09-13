"""
规则检测模块
用于检测翻译中的常见问题，如假名残留、断词处理不当等
"""

import re
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass


@dataclass
class RuleIssue:
    """规则检测问题"""
    issue_type: str  # 问题类型：kana, broken_word, repetition, etc.
    description: str  # 问题描述
    severity: str    # 严重程度：high, medium, low
    suggestion: str   # 改进建议


class RuleDetector:
    """规则检测器"""
    
    def __init__(self):
        # 假名字符范围
        self.kana_pattern = r'[\u3040-\u309F\u30A0-\u30FF\uFF66-\uFF9D]'
        
        # 断词模式：日文假名被符号分隔
        self.broken_word_pattern = r'[\u3040-\u309F\u30A0-\u30FF]+[・\-\~]+[\u3040-\u309F\u30A0-\u30FF]+'
        
        # 单独的假名字符（需要特别处理）
        self.single_kana_pattern = r'^[\u3040-\u309F\u30A0-\u30FF\uFF66-\uFF9D]+$'
        
        # 重复字符检测
        self.repetition_pattern = r'(.)\1{4,}'  # 同一字符重复5次以上
    
    def detect_kana_issues(self, text: str) -> List[RuleIssue]:
        """检测假名相关问题"""
        issues = []
        
        # 检测假名字符
        kana_matches = re.findall(self.kana_pattern, text)
        if kana_matches:
            # 检查是否包含单独的假名
            single_kana = re.findall(self.single_kana_pattern, text.strip())
            if single_kana:
                issues.append(RuleIssue(
                    issue_type="single_kana",
                    description=f"包含单独假名: {', '.join(single_kana)}",
                    severity="high",
                    suggestion="单独的假名需要翻译成语气词/拟声词或删除"
                ))
            else:
                issues.append(RuleIssue(
                    issue_type="kana",
                    description=f"包含假名字符: {', '.join(set(kana_matches))}",
                    severity="high",
                    suggestion="假名字符需要翻译成对应的中文"
                ))
        
        return issues
    
    def detect_broken_word_issues(self, text: str) -> List[RuleIssue]:
        """检测断词处理问题"""
        issues = []
        
        # 检测断词模式
        broken_words = re.findall(self.broken_word_pattern, text)
        if broken_words:
            issues.append(RuleIssue(
                issue_type="broken_word",
                description=f"断词处理不当: {', '.join(broken_words)}",
                severity="medium",
                suggestion="先翻译完整词，然后在中文词上添加原文的符号"
            ))
        
        return issues
    
    def detect_repetition_issues(self, text: str) -> List[RuleIssue]:
        """检测重复字符问题"""
        issues = []
        
        # 检测重复字符
        repetitions = re.findall(self.repetition_pattern, text)
        if repetitions:
            issues.append(RuleIssue(
                issue_type="repetition",
                description=f"包含过多重复字符: {', '.join(set(repetitions))}",
                severity="medium",
                suggestion="拟声词和感叹词重复时，控制在5次以内"
            ))
        
        return issues
    
    def detect_all_issues(self, original: str, translated: str) -> List[RuleIssue]:
        """检测所有问题"""
        issues = []
        
        # 检测假名问题
        issues.extend(self.detect_kana_issues(translated))
        
        # 检测断词问题
        issues.extend(self.detect_broken_word_issues(translated))
        
        # 检测重复问题
        issues.extend(self.detect_repetition_issues(translated))
        
        return issues
    
    def format_issues_for_prompt(self, issues: List[RuleIssue]) -> str:
        """将问题格式化为提示文本"""
        if not issues:
            return ""
        
        formatted = []
        for issue in issues:
            severity_emoji = {
                "high": "🔴",
                "medium": "🟡", 
                "low": "🟢"
            }.get(issue.severity, "⚪")
            
            formatted.append(f"{severity_emoji} {issue.description}")
            if issue.suggestion:
                formatted.append(f"   建议: {issue.suggestion}")
        
        return "\n".join(formatted)


def detect_translation_issues(original: str, translated: str) -> List[RuleIssue]:
    """便捷函数：检测翻译问题"""
    detector = RuleDetector()
    return detector.detect_all_issues(original, translated)


def format_issues_for_enhancement(issues: List[RuleIssue]) -> str:
    """便捷函数：格式化问题用于增强提示"""
    detector = RuleDetector()
    return detector.format_issues_for_prompt(issues)
