#!/usr/bin/env python3
"""
输出格式化工具
"""

def format_quality_output(result: str) -> str:
    """
    格式化质量检测输出
    
    Args:
        result: 质量检测结果
        
    Returns:
        格式化后的输出
    """
    if not result:
        return result
    
    # 提取GOOD/BAD结果
    result = result.strip().upper()
    
    # 查找最后的GOOD或BAD
    if result.endswith('GOOD'):
        return 'GOOD'
    elif result.endswith('BAD'):
        return 'BAD'
    
    # 如果包含这些词，返回最后一个
    good_pos = result.rfind('GOOD')
    bad_pos = result.rfind('BAD')
    
    if good_pos > bad_pos:
        return 'GOOD'
    elif bad_pos > good_pos:
        return 'BAD'
    
    return result
