#!/usr/bin/env python3
"""
Pixiv小说翻译器 - 简化版本

基于改进后的translate_pixiv_v1.py，保持功能完整但结构更清晰
"""

import sys
import os
from pathlib import Path

# 添加当前目录到Python路径
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir.parent))

# 导入改进后的翻译脚本
from src.scripts.translate_pixiv_v1 import main as translate_main

if __name__ == "__main__":
    translate_main()
