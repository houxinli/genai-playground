# tasks/translation/src/utils/validation

## 作用

纯函数级质量校验器目录，被在线 quality checker 和离线 QA gate 按需复用。

## 直接子项

- `__init__.py`：package 标记。
- `cjk_punctuation_check.py` / `cjk_punctuation_check_test.py`：中日标点校验与测试。
- `jp_copy_check.py` / `jp_copy_check_test.py`：日文照抄/假名残留校验与测试。
- `length_check.py` / `length_check_test.py`：长度异常校验与测试。
- `repetition_check.py` / `repetition_check_test.py`：重复文本校验与测试。
- `rule_qc_lines_test.py`：逐行规则 QC 测试。

## 维护规则

- 新校验器先明确服务在线重试还是离线放行。
- 保持纯函数，方便被不同 gate 组合调用。
