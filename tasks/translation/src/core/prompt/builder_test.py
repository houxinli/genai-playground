#!/usr/bin/env python3
"""
PromptBuilder单元测试
测试统一的prompt构建功能
"""

import pytest
from pathlib import Path
from .config import PromptConfig, create_config, create_test_config
from .builder import PromptBuilder


def validate_translation_preface_content(content):
    """验证翻译模式preface内容的辅助函数"""
    required_parts = [
        '将下列日语逐行翻译为中文',
        '不要解释、不要添加标额外内容',
        '严格按照行数输出',
        '引号使用原文用的方引号「」',
        '拟声词和感叹词重复时，控制在5次以内',
        '翻译完成后，在最后单独输出一行：[翻译完成]'
    ]
    
    for part in required_parts:
        assert part in content, f'Missing required translation preface part: {part}'


def validate_translation_terminology_content(content):
    """验证翻译模式术语表内容的辅助函数"""
    required_terms = [
        '术语对照表：',
        'こんにちは → 你好',
        '田中 → 田中',
        '天気 → 天气',
        'ありがとう → 谢谢',
        'テスト → 测试',
        '先生 → 先生',
        '今日 → 今天',
        'いい → 好',
        'ですね → 呢'
    ]
    
    for term in required_terms:
        assert term in content, f'Missing required terminology: {term}'


def validate_qc_preface_content(content):
    """验证QC模式preface内容的辅助函数"""
    required_parts = [
        '你是专业的翻译质量评估专家',
        '为每一行给出0-1之间的分数',
        '1.0: 完美翻译，准确传达原意',
        '0.8-0.9: 很好，略有小问题',
        '0.6-0.7: 一般，有明显问题',
        '0.4-0.5: 较差，有严重问题',
        '0.0-0.3: 很差，基本错误',
        '**严重扣分项**：中文译文出现日语假名',
        '必须判不及格(<0.6)',
        '请按行号顺序输出分数'
    ]
    
    for part in required_parts:
        assert part in content, f'Missing required QC preface part: {part}'


def validate_enhancement_preface_content(content):
    """验证增强模式preface内容的辅助函数"""
    required_parts = [
        '你是专业的中日互译编辑',
        '给定若干原文与当前译文',
        # 文案兼容：旧版为“请逐行改进质量”，新版为“逐行检查质量并优化翻译结果”
        '逐行检查质量并优化翻译结果',
        '仅输出改进后的中文译文',
        '不要任何解释',
        '保持原文的语气和风格',
        '使用更自然的中文表达',
        '保持专有名词的一致性',
        '引号使用原文的方引号「」',
        '拟声词和感叹词重复时，控制在5次以内',
        '翻译完成后，在最后单独输出一行：[翻译完成]'
    ]
    
    for part in required_parts:
        if isinstance(part, tuple):
            assert any(p in content for p in part), f"Missing required enhancement preface part (any): {part}"
        else:
            assert part in content, f'Missing required enhancement preface part: {part}'


def validate_enhancement_terminology_content(content):
    """验证增强模式术语表内容的辅助函数"""
    required_terms = [
        '术语对照表：',
        'こんにちは → 你好',
        '田中 → 田中',
        '天気 → 天气',
        'ありがとう → 谢谢',
        'テスト → 测试',
        '先生 → 先生',
        '今日 → 今天',
        'いい → 好',
        'ですね → 呢'
    ]
    
    for term in required_terms:
        assert term in content, f'Missing required terminology: {term}'


class TestPromptBuilder:
    """PromptBuilder测试类"""
    
    @pytest.fixture
    def prompt_dir(self):
        """prompt目录路径"""
        return Path(__file__).parent
    
    @pytest.fixture
    def test_config(self, prompt_dir):
        """测试配置"""
        return create_test_config("translation", prompt_dir)
    
    @pytest.fixture
    def builder(self, test_config):
        """PromptBuilder实例"""
        return PromptBuilder(test_config)
    
    def test_build_translation_messages(self, builder):
        """测试翻译模式的消息构建"""
        target_lines = ["こんにちは", "ありがとう"]
        
        messages = builder.build_messages(target_lines=target_lines)
        
        # 验证消息结构
        assert len(messages) >= 2  # 至少包含system和user消息
        assert messages[0]["role"] == "system"
        assert messages[-1]["role"] == "user"
        
        # 验证行号格式
        user_content = messages[-1]["content"]
        assert "1. こんにちは" in user_content
        assert "2. ありがとう" in user_content
    
    def test_build_qc_messages(self, prompt_dir):
        """测试QC模式的消息构建"""
        qc_config = create_test_config("qc", prompt_dir)
        qc_builder = PromptBuilder(qc_config)
        
        target_lines = ["こんにちは", "ありがとう"]
        translated_lines = ["你好", "谢谢"]
        
        messages = qc_builder.build_messages(
            target_lines=target_lines,
            translated_lines=translated_lines
        )
        
        # 验证消息结构
        assert len(messages) >= 2
        assert messages[0]["role"] == "system"
        assert messages[-1]["role"] == "user"
        
        # 验证QC格式
        user_content = messages[-1]["content"]
        assert "原文: こんにちは" in user_content
        assert "译文: 你好" in user_content
        assert "原文: ありがとう" in user_content
        assert "译文: 谢谢" in user_content
    
    def test_build_enhancement_messages(self, prompt_dir):
        """测试增强模式的消息构建"""
        enhancement_config = create_test_config("enhancement", prompt_dir)
        enhancement_builder = PromptBuilder(enhancement_config)
        
        target_lines = ["こんにちは", "ありがとう"]
        translated_lines = ["你好", "谢谢"]
        
        messages = enhancement_builder.build_messages(
            target_lines=target_lines,
            translated_lines=translated_lines
        )
        
        # 验证消息结构
        assert len(messages) >= 2
        assert messages[0]["role"] == "system"
        assert messages[-1]["role"] == "user"
        
        # 验证增强格式
        user_content = messages[-1]["content"]
        assert "原文: こんにちは" in user_content
        assert "现译: 你好" in user_content
        assert "原文: ありがとう" in user_content
        assert "现译: 谢谢" in user_content
    
    def test_previous_io_context(self, builder):
        """测试前一次输入输出的上下文"""
        target_lines = ["新しい文"]
        previous_input = ["前の文1", "前の文2"]
        previous_output = ["前文1", "前文2"]
        
        messages = builder.build_messages(
            target_lines=target_lines,
            previous_io=(previous_input, previous_output)
        )
        
        # 验证包含前一次的输入输出
        assert len(messages) >= 4  # system + few-shot + previous_io + current
        
        # 查找前一次输入输出的消息
        prev_input_found = False
        prev_output_found = False
        
        for msg in messages:
            if msg["role"] == "user" and "前の文1" in msg["content"]:
                prev_input_found = True
            elif msg["role"] == "assistant" and "前文1" in msg["content"]:
                prev_output_found = True
        
        assert prev_input_found, "前一次输入未找到"
        assert prev_output_found, "前一次输出未找到"
    
    def test_translation_mode_previous_io(self, prompt_dir):
        """测试翻译模式的previous_io功能"""
        config = create_test_config("translation", prompt_dir)
        builder = PromptBuilder(config)
        
        target_lines = ["新しい文1", "新しい文2"]
        previous_input = ["前の文1", "前の文2"]
        previous_output = ["前文1", "前文2"]
        previous_io = (previous_input, previous_output)
        
        messages = builder.build_messages(
            target_lines=target_lines,
            previous_io=previous_io
        )
        
        # 验证消息结构
        assert len(messages) >= 6  # system + few-shot + previous_io + current
        
        # 验证包含few-shot示例
        few_shot_user_found = False
        few_shot_assistant_found = False
        
        # 验证previous_io格式
        prev_user_found = False
        prev_assistant_found = False
        
        for i, msg in enumerate(messages):
            role = msg["role"]
            content = msg["content"]
            print(f"\n=== 消息 {i} ({role}) ===")
            for line in content.split('\n'):
                print(line)
            
            # 验证few-shot示例
            if role == "user" and "1. こんにちは、田中さん。" in content and "2. 今日はいい天気ですね。" in content:
                few_shot_user_found = True
                print("  ✓ 找到few-shot用户消息")
            elif role == "assistant" and "1. 你好，田中先生。" in content and "2. 今天天气不错呢。" in content and "[翻译完成]" in content:
                few_shot_assistant_found = True
                print("  ✓ 找到few-shot助手消息")
            # 验证previous_io
            elif role == "user" and "1. 前の文1" in content and "2. 前の文2" in content:
                prev_user_found = True
                print("  ✓ 找到previous_io用户消息")
            elif role == "assistant" and "1. 前文1" in content and "2. 前文2" in content and "[翻译完成]" in content:
                prev_assistant_found = True
                print("  ✓ 找到previous_io助手消息")
        
        assert few_shot_user_found, "翻译模式few-shot用户消息未找到"
        assert few_shot_assistant_found, "翻译模式few-shot助手消息未找到"
        assert prev_user_found, "翻译模式previous_io用户消息格式错误"
        assert prev_assistant_found, "翻译模式previous_io助手消息格式错误"
        
        # 验证当前输入的行号累计性（动态计算）
        current_msg = messages[-1]
        few_shot = builder._get_few_shot_line_count(config)
        current_start = few_shot + len(previous_input) + 1
        assert f"{current_start}. 新しい文1" in current_msg["content"], f"当前输入第1行应该是{current_start}. 新しい文1，实际内容：{current_msg['content']}"
        assert f"{current_start+1}. 新しい文2" in current_msg["content"], f"当前输入第2行应该是{current_start+1}. 新しい文2，实际内容：{current_msg['content']}"
        
        # 确保没有从1重新开始（使用更精确的匹配）
        lines = current_msg["content"].split('\n')
        for line in lines:
            if line.strip().startswith('1. 新しい文') and not line.strip().startswith('13. 新しい文'):
                assert False, "当前输入不应该从行号1重新开始"
            if line.strip().startswith('2. 新しい文') and not line.strip().startswith('14. 新しい文'):
                assert False, "当前输入不应该从行号2重新开始"
    
    def test_qc_mode_previous_io(self, prompt_dir):
        """测试QC模式的previous_io功能（QC模式现在支持previous_io）"""
        config = create_test_config("qc", prompt_dir)
        builder = PromptBuilder(config)
        
        target_lines = ["原文1", "原文2"]
        translated_lines = ["译文1", "译文2"]
        previous_input = ["前の文1", "前の文2"]
        previous_output = ["前文1", "前文2"]
        previous_io = (previous_input, previous_output)
        
        messages = builder.build_messages(
            target_lines=target_lines,
            translated_lines=translated_lines,
            previous_io=previous_io
        )
        
        # QC模式现在应该支持previous_io
        assert len(messages) >= 6  # system + few-shot + previous_io + current
        
        # 验证包含few-shot示例
        few_shot_user_found = False
        few_shot_assistant_found = False
        
        # 验证包含previous_io
        prev_user_found = False
        prev_assistant_found = False
        
        for i, msg in enumerate(messages):
            role = msg["role"]
            content = msg["content"]
            print(f"\n=== QC模式消息 {i} ({role}) ===")
            for line in content.split('\n'):
                print(line)
            
            # 验证few-shot示例
            if role == "user" and "1. 原文: こんにちは、田中さん。" in content and "1. 译文: 你好，田中先生。" in content:
                few_shot_user_found = True
                print("  ✓ 找到QC few-shot用户消息")
            elif role == "assistant" and "1. 0.9" in content and "4. 0.5" in content:
                few_shot_assistant_found = True
                print("  ✓ 找到QC few-shot助手消息")
            # 验证previous_io（QC模式从 few_shot+1 行开始）
            elif role == "user" and (f"{builder._get_few_shot_line_count(config)+1}. 前の文1" in content) and (f"{builder._get_few_shot_line_count(config)+2}. 前の文2" in content):
                prev_user_found = True
                print("  ✓ 找到QC previous_io用户消息")
            elif role == "assistant" and (f"{builder._get_few_shot_line_count(config)+1}. 前文1" in content) and (f"{builder._get_few_shot_line_count(config)+2}. 前文2" in content):
                prev_assistant_found = True
                print("  ✓ 找到QC previous_io助手消息")
        
        assert few_shot_user_found, "QC模式few-shot用户消息未找到"
        assert few_shot_assistant_found, "QC模式few-shot助手消息未找到"
        assert prev_user_found, "QC模式previous_io用户消息格式错误"
        assert prev_assistant_found, "QC模式previous_io助手消息格式错误"
        
        # 验证当前输入格式（QC模式的行号也应该累计）
        current_msg = messages[-1]
        few_shot = builder._get_few_shot_line_count(config)
        current_start = few_shot + len(previous_input) + 1
        assert f"{current_start}. 原文: 原文1" in current_msg["content"], f"QC模式当前输入第1行应该是{current_start}. 原文: 原文1，实际内容：{current_msg['content']}"
        assert f"{current_start}. 译文: 译文1" in current_msg["content"], f"QC模式当前输入第1行译文应该是{current_start}. 译文: 译文1，实际内容：{current_msg['content']}"
        assert f"{current_start+1}. 原文: 原文2" in current_msg["content"], f"QC模式当前输入第2行应该是{current_start+1}. 原文: 原文2，实际内容：{current_msg['content']}"
        assert f"{current_start+1}. 译文: 译文2" in current_msg["content"], f"QC模式当前输入第2行译文应该是{current_start+1}. 译文: 译文2，实际内容：{current_msg['content']}"
        
        # 确保没有从1重新开始（使用更精确的匹配）
        lines = current_msg["content"].split('\n')
        for line in lines:
            if line.strip().startswith('1. 原文:') and not line.strip().startswith('21. 原文:'):
                assert False, "QC模式当前输入不应该从行号1重新开始"
            if line.strip().startswith('2. 原文:') and not line.strip().startswith('22. 原文:'):
                assert False, "QC模式当前输入不应该从行号2重新开始"
    
    def test_enhancement_mode_previous_io(self, prompt_dir):
        """测试增强模式的previous_io功能（增强模式现在支持previous_io）"""
        config = create_test_config("enhancement", prompt_dir)
        builder = PromptBuilder(config)
        
        target_lines = ["原文1", "原文2"]
        translated_lines = ["现译1", "现译2"]
        previous_input = ["前の文1", "前の文2"]
        previous_output = ["前文1", "前文2"]
        previous_io = (previous_input, previous_output)
        
        messages = builder.build_messages(
            target_lines=target_lines,
            translated_lines=translated_lines,
            previous_io=previous_io
        )
        
        # 增强模式现在应该支持previous_io
        assert len(messages) >= 6  # system + few-shot + previous_io + current
        
        # 验证包含few-shot示例
        few_shot_user_found = False
        few_shot_assistant_found = False
        
        # 验证包含previous_io
        prev_user_found = False
        prev_assistant_found = False
        
        for i, msg in enumerate(messages):
            role = msg["role"]
            content = msg["content"]
            print(f"\n=== 增强模式消息 {i} ({role}) ===")
            for line in content.split('\n'):
                print(line)
            
            # 验证few-shot示例（允许示例开始标记导致索引移动）
            if role == "user" and ("1. 原文: こんにちは、田中さん。" in content and "2. 原文: 今日はいい天気ですね。" in content):
                few_shot_user_found = True
                print("  ✓ 找到增强模式few-shot用户消息")
            elif role == "assistant" and ("1. 你好，田中先生。" in content and "2. 今天天气不错呢。" in content) and "[翻译完成]" in content:
                few_shot_assistant_found = True
                print("  ✓ 找到增强模式few-shot助手消息")
            # 增强模式的previous_io使用"原文 + 现译"格式（从 few_shot+1 行开始）
            elif role == "user" and (f"{builder._get_few_shot_line_count(config)+1}. 原文: 前の文1" in content) and (f"{builder._get_few_shot_line_count(config)+1}. 现译: 前文1" in content):
                prev_user_found = True
                print("  ✓ 找到增强模式previous_io用户消息")
            elif role == "assistant" and (f"{builder._get_few_shot_line_count(config)+1}. 前文1" in content) and (f"{builder._get_few_shot_line_count(config)+2}. 前文2" in content) and "[翻译完成]" in content:
                prev_assistant_found = True
                print("  ✓ 找到增强模式previous_io助手消息")
        
        assert few_shot_user_found, "增强模式few-shot用户消息未找到"
        assert few_shot_assistant_found, "增强模式few-shot助手消息未找到"
        assert prev_user_found, "增强模式previous_io用户消息格式错误"
        assert prev_assistant_found, "增强模式previous_io助手消息格式错误"
        
        # 验证当前输入格式（增强模式的行号也应该累计）
        current_msg = messages[-1]
        few_shot = builder._get_few_shot_line_count(config)
        current_start = few_shot + len(previous_input) + 1
        assert f"{current_start}. 原文: 原文1" in current_msg["content"], f"增强模式当前输入第1行应该是{current_start}. 原文: 原文1，实际内容：{current_msg['content']}"
        assert f"{current_start}. 现译: 现译1" in current_msg["content"], f"增强模式当前输入第1行现译应该是{current_start}. 现译: 现译1，实际内容：{current_msg['content']}"
        assert f"{current_start+1}. 原文: 原文2" in current_msg["content"], f"增强模式当前输入第2行应该是{current_start+1}. 原文: 原文2，实际内容：{current_msg['content']}"
        assert f"{current_start+1}. 现译: 现译2" in current_msg["content"], f"增强模式当前输入第2行现译应该是{current_start+1}. 现译: 现译2，实际内容：{current_msg['content']}"
        
        # 确保没有从1重新开始（使用更精确的匹配）
        lines = current_msg["content"].split('\n')
        for line in lines:
            if line.strip().startswith('1. 原文: 原文') and not line.strip().startswith('22. 原文: 原文'):
                assert False, "增强模式当前输入不应该从行号1重新开始"
            if line.strip().startswith('2. 原文: 原文') and not line.strip().startswith('23. 原文: 原文'):
                assert False, "增强模式当前输入不应该从行号2重新开始"
    
    def test_few_shot_examples(self, builder):
        """测试few-shot示例"""
        target_lines = ["テスト"]
        
        messages = builder.build_messages(target_lines=target_lines)
        
        # 验证包含few-shot示例
        assert len(messages) >= 3  # system + few-shot + current
        
        # 查找few-shot消息
        few_shot_found = False
        for msg in messages:
            if msg["role"] in ["user", "assistant"] and "こんにちは" in msg["content"]:
                few_shot_found = True
                break
        
        assert few_shot_found, "Few-shot示例未找到"
    
    def test_line_numbering(self, builder):
        """测试行号标记"""
        target_lines = ["行1", "行2", "行3"]
        
        messages = builder.build_messages(target_lines=target_lines)
        
        # 验证行号格式
        user_content = messages[-1]["content"]
        lines = user_content.split('\n')
        
        assert "1. 行1" in lines
        assert "2. 行2" in lines
        assert "3. 行3" in lines
    
    def test_cumulative_line_numbering_with_previous_io(self, prompt_dir):
        """测试带previous_io时的行号累计逻辑"""
        config = create_test_config("translation", prompt_dir)
        builder = PromptBuilder(config)
        
        # 模拟多轮对话场景
        # 第1轮: 行1-2
        # 第2轮: 行3-4 (应该累计)
        target_lines = ["新しい文1", "新しい文2"]
        previous_input = ["前の文1", "前の文2"]
        previous_output = ["前文1", "前文2"]
        previous_io = (previous_input, previous_output)
        
        messages = builder.build_messages(
            target_lines=target_lines,
            previous_io=previous_io
        )
        
        # 验证消息结构
        assert len(messages) >= 6  # system + few-shot + previous_io + current
        
        # 验证previous_io的行号（应该从1开始）
        prev_user_found = False
        for msg in messages:
            content = msg["content"]
            if msg["role"] == "user" and "1. 前の文1" in content and "2. 前の文2" in content:
                prev_user_found = True
                break
        assert prev_user_found, "previous_io行号应该从1开始"
        
        # 验证当前输入的行号（应该从3开始累计）
        current_msg = messages[-1]
        current_content = current_msg["content"]
        
        # 关键测试：当前输入的行号应该累计，而不是从1重新开始
        assert "3. 新しい文1" in current_content, f"当前输入第1行应该是3. 新しい文1，实际内容：{current_content}"
        assert "4. 新しい文2" in current_content, f"当前输入第2行应该是4. 新しい文2，实际内容：{current_content}"
        
        # 确保没有从1重新开始
        assert "1. 新しい文1" not in current_content, "当前输入不应该从行号1重新开始"
        assert "2. 新しい文2" not in current_content, "当前输入不应该从行号2重新开始"
    
    def test_end_marker(self, builder):
        """测试结束标记"""
        target_lines = ["テスト"]
        
        messages = builder.build_messages(target_lines=target_lines)
        
        # 查找结束标记
        end_marker_found = False
        for msg in messages:
            if msg["role"] == "assistant" and "[翻译完成]" in msg["content"]:
                end_marker_found = True
                break
        
        assert end_marker_found, "结束标记未找到"
    
    def test_config_creation(self, prompt_dir):
        """测试配置创建"""
        # 测试正常配置
        normal_config = create_config("translation", prompt_dir)
        assert normal_config.mode == "translation"
        assert normal_config.data_dir == prompt_dir
        assert normal_config.preface_file == "assets/preface_translation.txt"
        
        # 测试测试配置
        test_config = create_test_config("translation", prompt_dir)
        assert test_config.mode == "translation"
        assert test_config.data_dir == prompt_dir
        assert test_config.preface_file == "assets/preface_translation.txt"
    
    def test_complete_translation_prompt_content(self, prompt_dir):
        """测试翻译模式的完整prompt内容"""
        config = create_test_config("translation", prompt_dir)
        builder = PromptBuilder(config)
        
        messages = builder.build_messages(target_lines=["新しい文", "テスト文"])
        
        # 验证消息数量（system + few-shot + current）
        assert len(messages) >= 3
        
        # 验证系统消息内容
        system_msg = messages[0]
        assert system_msg["role"] == "system"
        system_content = system_msg["content"]
        
        # 结构化验证preface和术语表内容
        validate_translation_preface_content(system_content)
        validate_translation_terminology_content(system_content)
        
        # 验证few-shot示例
        few_shot_user_msg = messages[1]
        assert few_shot_user_msg["role"] == "user"
        required_user_content = [
            '1. こんにちは、田中さん。',
            '2. 今日はいい天気ですね。',
            '3. ありがとうございます。'
        ]
        for content in required_user_content:
            assert content in few_shot_user_msg["content"], f'Missing user content: {content}'
        
        few_shot_assistant_msg = messages[2]
        assert few_shot_assistant_msg["role"] == "assistant"
        required_assistant_content = [
            '1. 你好，田中先生。',
            '2. 今天天气不错呢。',
            '3. 谢谢您。',
            '[翻译完成]'
        ]
        for content in required_assistant_content:
            assert content in few_shot_assistant_msg["content"], f'Missing assistant content: {content}'
        
        # 验证第二组few-shot示例
        few_shot_user_msg2 = messages[3]
        assert few_shot_user_msg2["role"] == "user"
        required_user_content2 = [
            '1. これはテストです。',
            '2. 先生に挨拶しました。'
        ]
        for content in required_user_content2:
            assert content in few_shot_user_msg2["content"], f'Missing user content 2: {content}'
        
        few_shot_assistant_msg2 = messages[4]
        assert few_shot_assistant_msg2["role"] == "assistant"
        required_assistant_content2 = [
            '1. 这是测试。',
            '2. 向老师打了招呼。',
            '[翻译完成]'
        ]
        for content in required_assistant_content2:
            assert content in few_shot_assistant_msg2["content"], f'Missing assistant content 2: {content}'
        
        # 验证当前输入
        current_msg = messages[-1]
        assert current_msg["role"] == "user"
        required_current_content = [
            '1. 新しい文',
            '2. テスト文'
        ]
        for content in required_current_content:
            assert content in current_msg["content"], f'Missing current content: {content}'
    
    def test_complete_qc_prompt_content(self, prompt_dir):
        """测试QC模式的完整prompt内容"""
        config = create_test_config("qc", prompt_dir)
        builder = PromptBuilder(config)
        
        messages = builder.build_messages(
            target_lines=["新しい文", "テスト文"],
            translated_lines=["新句子", "测试句子"]
        )
        
        # 验证消息数量（system + few-shot + current）
        assert len(messages) >= 3
        
        # 验证系统消息内容
        system_msg = messages[0]
        assert system_msg["role"] == "system"
        system_content = system_msg["content"]
        
        # 结构化验证preface内容
        validate_qc_preface_content(system_content)
        
        # QC模式不应该包含术语表
        assert "术语对照表：" not in system_content, "QC mode should not contain terminology"
        
        # 验证few-shot示例
        few_shot_user_msg = messages[1]
        assert few_shot_user_msg["role"] == "user"
        required_user_content = [
            '1. 原文: こんにちは、田中さん。',
            '1. 译文: 你好，田中先生。',
            '2. 原文: 今日はいい天気ですね。',
            '2. 译文: 今天天气不错呢。',
            '3. 原文: ありがとうございます。',
            '3. 译文: 谢谢您。',
            '4. 原文: これはテストです。',
            '4. 译文: これは测试です。'
        ]
        for content in required_user_content:
            assert content in few_shot_user_msg["content"], f'Missing QC user content: {content}'
        
        few_shot_assistant_msg = messages[2]
        assert few_shot_assistant_msg["role"] == "assistant"
        required_assistant_content = [
            '1. 0.9',
            '2. 0.8',
            '3. 0.9',
            '4. 0.5'
        ]
        for content in required_assistant_content:
            assert content in few_shot_assistant_msg["content"], f'Missing QC assistant content: {content}'
        
        # 验证当前输入格式（动态起始行号）
        current_msg = messages[-1]
        assert current_msg["role"] == "user"
        few_shot = builder._get_few_shot_line_count(config)
        start_ln = few_shot + 1
        required_current_content = [
            f'{start_ln}. 原文: 新しい文',
            f'{start_ln}. 译文: 新句子',
            f'{start_ln+1}. 原文: テスト文',
            f'{start_ln+1}. 译文: 测试句子'
        ]
        for content in required_current_content:
            assert content in current_msg["content"], f'Missing QC current content: {content}'
    
    def test_complete_enhancement_prompt_content(self, prompt_dir):
        """测试增强模式的完整prompt内容"""
        config = create_test_config("enhancement", prompt_dir)
        builder = PromptBuilder(config)
        
        messages = builder.build_messages(
            target_lines=["新しい文", "テスト文"],
            translated_lines=["新句子", "测试句子"]
        )
        
        # 验证消息数量（system + few-shot + current）
        assert len(messages) >= 3
        
        # 验证系统消息内容
        system_msg = messages[0]
        assert system_msg["role"] == "system"
        system_content = system_msg["content"]
        
        # 结构化验证preface和术语表内容
        validate_enhancement_preface_content(system_content)
        validate_enhancement_terminology_content(system_content)
        
        # 验证few-shot示例（允许示例开始/结束标记），检查关键行存在
        # few-shot第一块 user 消息可能出现在 messages[1] 或 [2]
        fs_user_idx = 2 if messages[1]["content"].startswith("1. [示例对话开始]") else 1
        few_shot_user_msg = messages[fs_user_idx]
        assert few_shot_user_msg["role"] == "user"
        for content in ['1. 原文: こんにちは、田中さん。', '2. 原文: 今日はいい天気ですね。', '3. 原文: ありがとうございます。']:
            assert content in few_shot_user_msg["content"], f'Missing enhancement user content: {content}'
        
        few_shot_assistant_msg = messages[2]
        assert few_shot_assistant_msg["role"] == "assistant"
        required_assistant_content = [
            '1. 你好，田中先生。',
            '2. 今天天气不错呢。',
            '3. 非常感谢您。',
            '[翻译完成]'
        ]
        for content in required_assistant_content:
            assert content in few_shot_assistant_msg["content"], f'Missing enhancement assistant content: {content}'
        
        # 验证当前输入格式
        current_msg = messages[-1]
        assert current_msg["role"] == "user"
        required_current_content = [
            '1. 原文: 新しい文',
            '1. 现译: 新句子',
            '2. 原文: テスト文',
            '2. 现译: 测试句子'
        ]
        for content in required_current_content:
            assert content in current_msg["content"], f'Missing enhancement current content: {content}'

    def test_build_messages_with_start_no_previous_io(self, prompt_dir):
        """无 previous_io 时，build_messages_with_start 返回的起始行号应为 few-shot 原文数 + 1"""
        config = create_test_config("enhancement", prompt_dir)
        builder = PromptBuilder(config)

        # 计算few-shot原文行数
        few_shot_count = builder._get_few_shot_line_count(config)

        target_lines = ["原文A", "原文B", "原文C"]
        translated_lines = ["现译A", "现译B", "现译C"]

        messages, start_ln = builder.build_messages_with_start(
            target_lines=target_lines,
            translated_lines=translated_lines,
            previous_io=None
        )

        assert start_ln == few_shot_count + 1

        # 校验消息中的首行编号与返回的起始行号一致
        current_msg = messages[-1]
        content = current_msg["content"].split("\n")
        assert any(line.startswith(f"{start_ln}. 原文: ") for line in content)

    def test_build_messages_with_start_with_previous_io(self, prompt_dir):
        """有 previous_io 时，起始行号应为 few-shot 原文数 + len(previous_io.input_lines) + 1"""
        config = create_test_config("enhancement", prompt_dir)
        builder = PromptBuilder(config)

        few_shot_count = builder._get_few_shot_line_count(config)

        previous_input = ["前の文1", "前の文2", "前の文3", "前の文4", "前の文5"]
        previous_output = ["前文1", "前文2", "前文3", "前文4", "前文5"]
        previous_io = (previous_input, previous_output)

        target_lines = ["原文A", "原文B"]
        translated_lines = ["现译A", "现译B"]

        messages, start_ln = builder.build_messages_with_start(
            target_lines=target_lines,
            translated_lines=translated_lines,
            previous_io=previous_io
        )

        assert start_ln == few_shot_count + len(previous_input) + 1

        # 校验previous_io段行号正确（从 few_shot_count + 1 开始）
        prev_user_found = False
        expected_prev_start = few_shot_count + 1
        for msg in messages:
            if msg["role"] == "user" and f"{expected_prev_start}. 原文: 前の文1" in msg["content"]:
                prev_user_found = True
                break
        assert prev_user_found, "previous_io 用户消息编号起点不正确"

        # 校验当前输入首行编号与返回的起始行号一致
        current_msg = messages[-1]
        content = current_msg["content"].split("\n")
        assert any(line.startswith(f"{start_ln}. 原文: ") for line in content)


if __name__ == "__main__":
    # 简单的手动测试
    prompt_dir = Path(__file__).parent
    test_config = create_test_config("translation", prompt_dir)
    builder = PromptBuilder(test_config)
    
    print("=== 测试翻译模式 ===")
    messages = builder.build_messages(target_lines=["こんにちは", "ありがとう"])
    for i, msg in enumerate(messages):
        print(f"[{i}] {msg['role']}: {msg['content'][:100]}...")
    
    print("\n=== 测试QC模式 ===")
    qc_config = create_test_config("qc", prompt_dir)
    qc_builder = PromptBuilder(qc_config)
    messages = qc_builder.build_messages(
        target_lines=["こんにちは"],
        translated_lines=["你好"]
    )
    for i, msg in enumerate(messages):
        print(f"[{i}] {msg['role']}: {msg['content'][:100]}...")
    
    print("\n=== 测试增强模式 ===")
    enhancement_config = create_test_config("enhancement", prompt_dir)
    enhancement_builder = PromptBuilder(enhancement_config)
    messages = enhancement_builder.build_messages(
        target_lines=["こんにちは"],
        translated_lines=["你好"]
    )
    for i, msg in enumerate(messages):
        print(f"[{i}] {msg['role']}: {msg['content'][:100]}...")
