"""
Prompt构建配置
定义各模式的prompt配置
"""

from dataclasses import dataclass
from typing import Dict, Optional
from pathlib import Path


@dataclass
class PromptConfig:
    """Prompt构建配置"""
    
    # 模式名称
    mode: str
    
    # 文件路径配置
    data_dir: Path
    preface_file: str
    sample_file: str
    terminology_file: Optional[str] = None
    
    # 格式配置
    use_line_numbers: bool = True
    use_end_marker: bool = True
    end_marker: str = "[翻译完成]"
    
    # 上下文配置
    support_context: bool = True
    support_previous_io: bool = True
    
    # 其他配置
    max_context_lines: int = 5


# 各模式的默认配置（不包含data_dir，需要在使用时设置）
TRANSLATION_CONFIG = PromptConfig(
    mode="translation",
    data_dir=Path(""),  # 占位符，实际使用时会被替换
    preface_file="assets/preface_translation.txt",
    sample_file="assets/sample_translation.txt",
    terminology_file="assets/terminology.txt",
    use_line_numbers=True,
    use_end_marker=True,
    end_marker="[翻译完成]",
    support_context=True,
    support_previous_io=True,
    max_context_lines=5
)

QC_CONFIG = PromptConfig(
    mode="qc",
    data_dir=Path(""),  # 占位符，实际使用时会被替换
    preface_file="assets/preface_qc.txt",
    sample_file="assets/sample_qc.txt",
    use_line_numbers=True,
    use_end_marker=True,
    end_marker="[检查完成]",
    support_context=False,
    support_previous_io=True,
    max_context_lines=0
)

ENHANCEMENT_CONFIG = PromptConfig(
    mode="enhancement",
    data_dir=Path(""),  # 占位符，实际使用时会被替换
    preface_file="assets/preface_enhancement.txt",
    sample_file="assets/sample_enhancement.txt",
    terminology_file="assets/terminology.txt",
    use_line_numbers=True,
    use_end_marker=True,
    end_marker="[翻译完成]",
    support_context=True,
    support_previous_io=True,
    max_context_lines=5
)

# 测试配置（使用脱敏的测试文件）
TEST_TRANSLATION_CONFIG = PromptConfig(
    mode="translation",
    data_dir=Path(""),  # 占位符，实际使用时会被替换
    preface_file="assets/preface_translation.txt",
    sample_file="assets/sample_translation.txt",
    terminology_file="assets/terminology.txt",
    use_line_numbers=True,
    use_end_marker=True,
    end_marker="[翻译完成]",
    support_context=True,
    support_previous_io=True,
    max_context_lines=5
)

TEST_QC_CONFIG = PromptConfig(
    mode="qc",
    data_dir=Path(""),  # 占位符，实际使用时会被替换
    preface_file="assets/preface_qc.txt",
    sample_file="assets/sample_qc.txt",
    use_line_numbers=True,
    use_end_marker=True,
    end_marker="[检查完成]",
    support_context=False,
    support_previous_io=True,
    max_context_lines=0
)

TEST_ENHANCEMENT_CONFIG = PromptConfig(
    mode="enhancement",
    data_dir=Path(""),  # 占位符，实际使用时会被替换
    preface_file="assets/preface_enhancement.txt",
    sample_file="assets/sample_enhancement.txt",
    terminology_file="assets/terminology.txt",
    use_line_numbers=True,
    use_end_marker=True,
    end_marker="[翻译完成]",
    support_context=True,
    support_previous_io=True,
    max_context_lines=5
)

# 配置映射
CONFIG_MAP = {
    "translation": TRANSLATION_CONFIG,
    "bilingual_simple": TRANSLATION_CONFIG,
    "qc": QC_CONFIG,
    "enhancement": ENHANCEMENT_CONFIG,
    "enhanced": ENHANCEMENT_CONFIG,
}

# 测试配置映射
TEST_CONFIG_MAP = {
    "translation": TEST_TRANSLATION_CONFIG,
    "bilingual_simple": TEST_TRANSLATION_CONFIG,
    "qc": TEST_QC_CONFIG,
    "enhancement": TEST_ENHANCEMENT_CONFIG,
    "enhanced": TEST_ENHANCEMENT_CONFIG,
}


def create_test_config(mode: str, data_dir: Path) -> PromptConfig:
    """创建测试模式的配置"""
    if mode not in TEST_CONFIG_MAP:
        raise ValueError(f"未知的模式: {mode}")
    
    # 复制测试配置并设置data_dir
    base_config = TEST_CONFIG_MAP[mode]
    return PromptConfig(
        mode=base_config.mode,
        data_dir=data_dir,
        preface_file=base_config.preface_file,
        sample_file=base_config.sample_file,
        terminology_file=base_config.terminology_file,
        use_line_numbers=base_config.use_line_numbers,
        use_end_marker=base_config.use_end_marker,
        end_marker=base_config.end_marker,
        support_context=base_config.support_context,
        support_previous_io=base_config.support_previous_io,
        max_context_lines=base_config.max_context_lines
    )


def create_config(mode: str, data_dir: Path) -> PromptConfig:
    """创建指定模式的配置"""
    if mode not in CONFIG_MAP:
        raise ValueError(f"未知的模式: {mode}")
    
    # 复制配置并设置data_dir
    base_config = CONFIG_MAP[mode]
    return PromptConfig(
        mode=base_config.mode,
        data_dir=data_dir,
        preface_file=base_config.preface_file,
        sample_file=base_config.sample_file,
        terminology_file=base_config.terminology_file,
        use_line_numbers=base_config.use_line_numbers,
        use_end_marker=base_config.use_end_marker,
        end_marker=base_config.end_marker,
        support_context=base_config.support_context,
        support_previous_io=base_config.support_previous_io,
        max_context_lines=base_config.max_context_lines
    )


def get_config(mode: str) -> PromptConfig:
    """获取指定模式的配置（已废弃，使用create_config）"""
    if mode not in CONFIG_MAP:
        raise ValueError(f"未知的模式: {mode}")
    return CONFIG_MAP[mode]


def get_test_config(mode: str) -> PromptConfig:
    """获取指定模式的测试配置（已废弃，使用create_config）"""
    if mode not in TEST_CONFIG_MAP:
        raise ValueError(f"未知的模式: {mode}")
    return TEST_CONFIG_MAP[mode]
