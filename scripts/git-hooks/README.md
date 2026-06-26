# scripts/git-hooks

## 作用

保存可安装到 `.git/hooks/` 的仓库 hook 模板。

## 直接子项

- `pre-push`：push 前运行的快速检查入口，由 `scripts/install-git-hooks.sh` 安装。

## 维护规则

- Hook 内容应保持快速、确定性，避免隐藏的网络依赖。
