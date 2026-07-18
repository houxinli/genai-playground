# 陪读复合词完整读音

## 背景

錆流浪全量陪读 dogfood 连续两篇出现同类语义错误:注解保留了原文骨架,但复合词括号里只写最后一个汉字或后缀的读音。机械骨架校验因此会通过,读者却会误以为这个不完整读音对应括号前的整个词。

## 改动

- annotate skill 把完整读音加入每批自检项。
- 核心规则明确:括号紧跟哪个完整词,读音就必须完整覆盖哪个词。
- 指南加入片假名加汉字、数量表达和汉字复合词的正反例。

本次不新增 QC 层。完整读音属于执行器语义判断,先用更简单明确的规则约束便宜模型,并继续在每篇发布前人工抽查。

## 验证

- `make agent-validate`
- `make docs-drift`
- `conda run -n llm python -m pytest tasks/translation/src -q`（475 passed）
- `git diff --check`

## 关联

- Issue #187
- Campaign #185
