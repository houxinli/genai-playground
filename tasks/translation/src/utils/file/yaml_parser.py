#!/usr/bin/env python3
"""
YAML解析工具
"""

from typing import Tuple, Optional, Dict


def parse_yaml_front_matter(content: str) -> Tuple[Optional[Dict], str]:
    """
    解析YAML front matter
    
    Args:
        content: 文件内容
        
    Returns:
        (YAML数据, 文本内容)
    """
    if not content.startswith('---'):
        return None, content
    
    try:
        import yaml
        parts = content.split('---', 2)
        if len(parts) < 3:
            return None, content
        
        yaml_content = parts[1].strip()
        text_content = parts[2].strip()
        
        yaml_data = yaml.safe_load(yaml_content)
        return yaml_data, text_content
    except Exception:
        return None, content
