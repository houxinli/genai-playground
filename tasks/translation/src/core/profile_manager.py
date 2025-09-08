#!/usr/bin/env python3
"""
Profile管理模块
统一管理所有生成参数和profile配置
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Any, Union
import json


@dataclass
class GenerationParams:
    """统一的生成参数类"""
    temperature: float = 0.7
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None
    stop: Optional[list] = None
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    repetition_penalty: float = 1.0
    no_repeat_ngram_size: int = 0
    log_prefix: str = "模型输出"
    watchdog_timeout_s: Optional[int] = None
    sentinel_prefix: Optional[str] = None
    enable_repeat_guard: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'temperature': self.temperature,
            'top_p': self.top_p,
            'max_tokens': self.max_tokens,
            'stop': self.stop,
            'frequency_penalty': self.frequency_penalty,
            'presence_penalty': self.presence_penalty,
            'repetition_penalty': self.repetition_penalty,
            'no_repeat_ngram_size': self.no_repeat_ngram_size,
            'log_prefix': self.log_prefix,
            'watchdog_timeout_s': self.watchdog_timeout_s,
            'sentinel_prefix': self.sentinel_prefix,
            'enable_repeat_guard': self.enable_repeat_guard,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GenerationParams':
        """从字典创建实例"""
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


class ProfileManager:
    """Profile管理器"""
    
    def __init__(self, profiles_file: Optional[Path] = None):
        self.profiles_file = profiles_file
        self._profiles = self._load_profiles()
    
    def _load_profiles(self) -> Dict[str, Dict[str, Any]]:
        """加载profile配置"""
        defaults = {
            "yaml": {
                "temperature": 0.0,
                "top_p": 1.0,
                "frequency_penalty": 0.0,
                "presence_penalty": 0.0,
                "repetition_penalty": 1.0,
                "no_repeat_ngram_size": 0,
                "max_tokens": 800,
                "stop": None,
                "watchdog_timeout_s": 180,
                "log_prefix": "YAML翻译"
            },
            "body": {
                "temperature": 0.7,
                "top_p": 0.9,
                "frequency_penalty": 0.3,
                "presence_penalty": 0.2,
                "repetition_penalty": 1.0,
                "no_repeat_ngram_size": 0,
                "max_tokens": 2000,
                "stop": ["（未完待续）", "[END]", "<|im_end|>", "</s>"],
                "watchdog_timeout_s": 0,
                "log_prefix": "正文翻译"
            },
            "bilingual_simple": {
                "temperature": 0.0,
                "top_p": 1.0,
                "frequency_penalty": 0.0,
                "presence_penalty": 0.0,
                "repetition_penalty": 1.0,
                "no_repeat_ngram_size": 0,
                "max_tokens": 6000,  # 上限
                "stop": None,
                "watchdog_timeout_s": 300,
                "log_prefix": "简化翻译",
                "enable_repeat_guard": True
            },
            "quality_check": {
                "temperature": 0.1,
                "top_p": 0.8,
                "frequency_penalty": 0.0,
                "presence_penalty": 0.0,
                "repetition_penalty": 1.0,
                "no_repeat_ngram_size": 0,
                "max_tokens": 1500,  # 提高QC可用生成，避免思考被截断
                "stop": None,
                "watchdog_timeout_s": 300,
                "log_prefix": "质量检测"
            }
        }
        
        # 尝试加载外部profile文件
        if self.profiles_file and self.profiles_file.exists():
            try:
                with open(self.profiles_file, 'r', encoding='utf-8') as f:
                    external = json.load(f)
                # 合并外部配置
                for profile_name, profile_config in external.items():
                    if profile_name in defaults:
                        defaults[profile_name].update(profile_config)
                    else:
                        defaults[profile_name] = profile_config
            except Exception as e:
                print(f"警告：加载profile文件失败，使用默认配置: {e}")
        
        return defaults
    
    def get_profile(self, profile_name: str) -> Dict[str, Any]:
        """获取指定profile的配置"""
        return self._profiles.get(profile_name, {})
    
    def get_generation_params(self, profile_name: str, **overrides) -> GenerationParams:
        """获取指定profile的生成参数"""
        profile_config = self.get_profile(profile_name)
        
        # 应用覆盖参数
        if overrides:
            profile_config = {**profile_config, **overrides}
        
        return GenerationParams.from_dict(profile_config)
    
    def update_profile(self, profile_name: str, config: Dict[str, Any]):
        """更新profile配置"""
        if profile_name not in self._profiles:
            self._profiles[profile_name] = {}
        self._profiles[profile_name].update(config)
    
    def save_profiles(self, file_path: Optional[Path] = None):
        """保存profile配置到文件"""
        target_file = file_path or self.profiles_file
        if target_file:
            with open(target_file, 'w', encoding='utf-8') as f:
                json.dump(self._profiles, f, ensure_ascii=False, indent=2)
    
    def list_profiles(self) -> list:
        """列出所有可用的profile"""
        return list(self._profiles.keys())
    
    def get_profile_info(self, profile_name: str) -> Dict[str, Any]:
        """获取profile的详细信息"""
        profile = self.get_profile(profile_name)
        return {
            'name': profile_name,
            'config': profile,
            'description': self._get_profile_description(profile_name)
        }
    
    def _get_profile_description(self, profile_name: str) -> str:
        """获取profile的描述"""
        descriptions = {
            'yaml': 'YAML元数据翻译，使用确定性参数确保格式正确',
            'body': '正文翻译，平衡质量和创造性',
            'bilingual_simple': '简化双语翻译，使用确定性参数和代码拼接',
            'quality_check': '质量检测，使用低温度确保稳定输出'
        }
        return descriptions.get(profile_name, '自定义profile')
