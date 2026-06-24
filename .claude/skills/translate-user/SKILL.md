---
name: translate-user
description: 一句话翻译一个作者的全部作品(端到端)。当用户说"用 xx 翻译 https://www.pixiv.net/users/<id>/novels"或"翻译整个作者/用户"时使用。executor 可插拔(openrouter 全自动;cursor/claude 为 agent 译者)。
argument-hint: "<pixiv/fanbox 用户 URL 或 id> [executor=openrouter] [limit=N]"
allowed-tools: Bash(make translate-user *), Bash(make pixiv-download *), Bash(make fanbox-download *), Read
---

# translate-user

把「下载 → 逐篇翻译 → 评估 → 保守择优 → 发布 → 渲染 → 合并整本」收成一条命令。
真相源:`tasks/translation/src/core/translate_user.py`(本文件只是薄壳)。

## 步骤

1. **解析用户**:从 URL 取 `provider`(pixiv/fanbox)与 `user_id`(如 `.../users/18330282/novels` → pixiv, 18330282)。
2. **确保已下载**:若 `tasks/translation/data/<provider>/<user_id>/` 无源 txt,先
   `make pixiv-download USER_ID=<id>`(fanbox 用 `make fanbox-download CREATOR_ID=<id>`)。
3. **端到端翻译**(executor 可插拔):
   ```
   make translate-user PROVIDER=<p> SOURCE=tasks/translation/data/<p>/<id> \
     STORE=tasks/translation/data/workspaces/<p>-<id>/store \
     RENDER=tasks/translation/data/workspaces/<p>-<id>/rendered \
     EXECUTOR=openrouter [BILINGUAL=<已有译文目录,作 incumbent>] [LIMIT=<先试 N 篇>]
   ```
   - `EXECUTOR=openrouter`:用 OpenRouter `x-ai/grok-4.3` **全自动**翻译(需 `OPENROUTER_API_KEY`)。
   - 产物:`RENDER/` 下逐篇 `<sid>.bilingual.txt` / `.zh.txt` + 按作者合并的 `<id>.bilingual.txt` / `<id>.zh.txt` + `translate_manifest.json`。
4. **看报告**:`translate_manifest.json` 的 summary(篇数/已发布/错误)与 merged(整本路径)。

## 边界与提示

- **成本**:整作者 = 大量付费调用。先用 `LIMIT=1` 试一篇,确认效果再放大。
- **executor 插拔**:`openrouter` 已通(全自动)。`cursor`/`claude`(agent 当译者)需 prepare/finish 拆分(尚未实现);在此之前 agent 路线用单篇 `translate-job` skill。
- 已有 legacy 译文时传 `BILINGUAL=`:旧译作 incumbent,新译作 challenger,保守择优自动选更优(旧译是日文/坏 → 选新译)。
- 本 skill 只编排,不改发布策略;保守择优与发布(原子 CAS)由底层保证。
