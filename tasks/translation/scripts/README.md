# scripts 目录说明

该目录存放与翻译流水线配套的辅助脚本。

## cleanup_bad_outputs.py
- 作用：清理存在 few-shot 泄漏样例、或译文中大段复制原文（日文片段）的双语输出文件。
- 用法：
  ```bash
  python scripts/cleanup_bad_outputs.py \
    --bilingual-dir tasks/translation/data/pixiv/<数据集>_bilingual \
    --original-dir  tasks/translation/data/pixiv/<数据集>
  ```
- 参数：
  - `--copy-threshold`: 判定“复制原文”行数阈值（默认 10）。
- 建议：先在小样本目录上验证；如需安全模式，可新增 `--dry-run` 仅打印而不删除。

## 已删除脚本
- `batch_translate_improved.py`：已废弃，统一使用 `tasks/translation/translate` / `src/translate.py`。

## 其他建议
- 新增脚本前优先考虑能否通过 `src/translate.py` 的参数直接覆盖使用场景。
- 若确需脚本，请在此 README 中补充用途、参数与示例，避免重复功能。
