# Translation Docs

本目录区分目标设计与当前操作手册：

- 目标系统设计：[`system-design.md`](system-design.md)
- 主文档：[`tasks/translation/README.md`](../README.md)
- 脚本说明：[`tasks/translation/scripts/README.md`](../scripts/README.md)

如果要改数据模型、QA/repair、Agent workflow、版本或用户反馈，先读目标系统设计。

如果只要执行当前管线，直接看主文档中的三段流程：

1. 下载（Pixiv / Fanbox）
2. 翻译（vLLM + bilingual-simple）
3. 修复与清理（repair/cleanup）
