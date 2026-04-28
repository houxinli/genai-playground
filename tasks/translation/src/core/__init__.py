#!/usr/bin/env python3
"""
翻译核心模块
"""

from importlib import import_module


_EXPORTS = {
    "TranslationConfig": ".config",
    "ProfileManager": ".profile_manager",
    "GenerationParams": ".profile_manager",
    "StreamingHandler": ".streaming_handler",
    "Translator": ".translator",
    "QualityChecker": ".quality_checker",
    "UnifiedLogger": ".logger",
    "TranslationPipeline": ".pipeline",
    "FileHandler": ".file_handler",
}

__all__ = [
    'TranslationConfig',
    'ProfileManager', 
    'GenerationParams',
    'StreamingHandler',
    'Translator',
    'QualityChecker',
    'UnifiedLogger',
    'TranslationPipeline',
    'FileHandler'
]


def __getattr__(name: str):
    """Lazy-load core exports so test discovery can import the package safely."""
    module_name = _EXPORTS.get(name)
    if not module_name:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    try:
        module = import_module(module_name, __name__)
    except ImportError as exc:
        if __name__ != "core" or "attempted relative import" not in str(exc):
            raise
        module = import_module(f"tasks.translation.src.core{module_name}")
    value = getattr(module, name)
    globals()[name] = value
    return value
