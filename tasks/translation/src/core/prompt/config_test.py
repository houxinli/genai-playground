#!/usr/bin/env python3
"""
PromptConfig单元测试
测试配置创建和管理功能
"""

import pytest
from pathlib import Path
from .config import PromptConfig, create_config, create_test_config, CONFIG_MAP, TEST_CONFIG_MAP


class TestPromptConfig:
    """PromptConfig测试类"""
    
    @pytest.fixture
    def prompt_dir(self):
        """prompt目录路径"""
        return Path(__file__).parent
    
    def test_prompt_config_creation(self, prompt_dir):
        """测试PromptConfig创建"""
        config = PromptConfig(
            mode="test",
            data_dir=prompt_dir,
            preface_file="test.txt",
            sample_file="test.txt",
            terminology_file="test.txt"
        )
        
        assert config.mode == "test"
        assert config.data_dir == prompt_dir
        assert config.preface_file == "test.txt"
        assert config.sample_file == "test.txt"
        assert config.terminology_file == "test.txt"
        assert config.use_line_numbers is True
        assert config.use_end_marker is True
        assert config.end_marker == "[翻译完成]"
    
    def test_create_config_normal_mode(self, prompt_dir):
        """测试创建正常模式配置"""
        config = create_config("translation", prompt_dir)
        
        assert config.mode == "translation"
        assert config.data_dir == prompt_dir
        assert config.preface_file == "assets/preface_translation.txt"
        assert config.sample_file == "assets/sample_translation.txt"
        assert config.terminology_file == "assets/terminology.txt"
        assert config.use_line_numbers is True
        assert config.use_end_marker is True
    
    def test_create_config_qc_mode(self, prompt_dir):
        """测试创建QC模式配置"""
        config = create_config("qc", prompt_dir)
        
        assert config.mode == "qc"
        assert config.data_dir == prompt_dir
        assert config.preface_file == "assets/preface_qc.txt"
        assert config.sample_file == "assets/sample_qc.txt"
        assert config.terminology_file is None
        assert config.use_line_numbers is True
        assert config.use_end_marker is False
    
    def test_create_config_enhancement_mode(self, prompt_dir):
        """测试创建增强模式配置"""
        config = create_config("enhancement", prompt_dir)
        
        assert config.mode == "enhancement"
        assert config.data_dir == prompt_dir
        assert config.preface_file == "assets/preface_enhancement.txt"
        assert config.sample_file == "assets/sample_enhancement.txt"
        assert config.terminology_file == "assets/terminology.txt"
        assert config.use_line_numbers is True
        assert config.use_end_marker is True
    
    def test_create_test_config_translation(self, prompt_dir):
        """测试创建翻译测试配置"""
        config = create_test_config("translation", prompt_dir)
        
        assert config.mode == "translation"
        assert config.data_dir == prompt_dir
        assert config.preface_file == "assets/preface_translation.txt"
        assert config.sample_file == "assets/sample_translation.txt"
        assert config.terminology_file == "assets/terminology.txt"
        assert config.use_line_numbers is True
        assert config.use_end_marker is True
    
    def test_create_test_config_qc(self, prompt_dir):
        """测试创建QC测试配置"""
        config = create_test_config("qc", prompt_dir)
        
        assert config.mode == "qc"
        assert config.data_dir == prompt_dir
        assert config.preface_file == "assets/preface_qc.txt"
        assert config.sample_file == "assets/sample_qc.txt"
        assert config.terminology_file is None
        assert config.use_line_numbers is True
        assert config.use_end_marker is False
    
    def test_create_test_config_enhancement(self, prompt_dir):
        """测试创建增强测试配置"""
        config = create_test_config("enhancement", prompt_dir)
        
        assert config.mode == "enhancement"
        assert config.data_dir == prompt_dir
        assert config.preface_file == "assets/preface_enhancement.txt"
        assert config.sample_file == "assets/sample_enhancement.txt"
        assert config.terminology_file == "assets/terminology.txt"
        assert config.use_line_numbers is True
        assert config.use_end_marker is True
    
    def test_config_map_completeness(self):
        """测试配置映射的完整性"""
        expected_modes = ["translation", "bilingual_simple", "qc", "enhancement", "enhanced"]
        
        for mode in expected_modes:
            assert mode in CONFIG_MAP, f"模式 {mode} 不在CONFIG_MAP中"
            config = CONFIG_MAP[mode]
            assert isinstance(config, PromptConfig)
            assert config.mode in ["translation", "qc", "enhancement"]
    
    def test_test_config_map_completeness(self):
        """测试测试配置映射的完整性"""
        expected_modes = ["translation", "bilingual_simple", "qc", "enhancement", "enhanced"]
        
        for mode in expected_modes:
            assert mode in TEST_CONFIG_MAP, f"模式 {mode} 不在TEST_CONFIG_MAP中"
            config = TEST_CONFIG_MAP[mode]
            assert isinstance(config, PromptConfig)
            assert config.mode in ["translation", "qc", "enhancement"]
    
    def test_invalid_mode_raises_error(self, prompt_dir):
        """测试无效模式抛出错误"""
        with pytest.raises(ValueError, match="未知的模式"):
            create_config("invalid_mode", prompt_dir)
        
        with pytest.raises(ValueError, match="未知的模式"):
            create_test_config("invalid_mode", prompt_dir)
    
    def test_config_defaults(self, prompt_dir):
        """测试配置默认值"""
        config = PromptConfig(
            mode="test",
            data_dir=prompt_dir,
            preface_file="test.txt",
            sample_file="test.txt"
        )
        
        # 测试默认值
        assert config.terminology_file is None
        assert config.use_line_numbers is True
        assert config.use_end_marker is True
        assert config.end_marker == "[翻译完成]"
        assert config.support_context is True
        assert config.support_previous_io is True
        assert config.max_context_lines == 5


if __name__ == "__main__":
    # 简单的手动测试
    prompt_dir = Path(__file__).parent
    
    print("=== 测试配置创建 ===")
    
    # 测试正常配置
    config = create_config("translation", prompt_dir)
    print(f"正常配置: {config.mode}, {config.preface_file}")
    
    # 测试测试配置
    test_config = create_test_config("translation", prompt_dir)
    print(f"测试配置: {test_config.mode}, {test_config.preface_file}")
    
    # 测试QC配置
    qc_config = create_test_config("qc", prompt_dir)
    print(f"QC配置: {qc_config.mode}, {qc_config.preface_file}, end_marker={qc_config.use_end_marker}")
    
    # 测试增强配置
    enhancement_config = create_test_config("enhancement", prompt_dir)
    print(f"增强配置: {enhancement_config.mode}, {enhancement_config.preface_file}")
    
    print("\n=== 测试完成 ===")
