#!/usr/bin/env bash
# Symlink the version-controlled git hooks in scripts/git-hooks/ into .git/hooks/.
# Re-run safely any time; it overwrites existing symlinks.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
SRC_DIR="$REPO_ROOT/scripts/git-hooks"
# worktree/submodule 下 .git 是文件而非目录,让 Git 解析真实 hooks 路径。
# --git-path 返回相对 CWD 的路径,必须先 cd 到仓库根再解析。
cd "$REPO_ROOT"
DEST_DIR="$(git rev-parse --git-path hooks)"
case "$DEST_DIR" in
  /*) ;;
  *) DEST_DIR="$REPO_ROOT/$DEST_DIR" ;;
esac

if [ ! -d "$SRC_DIR" ]; then
  echo "No hooks directory at $SRC_DIR" >&2
  exit 1
fi

mkdir -p "$DEST_DIR"
for hook in "$SRC_DIR"/*; do
  name="$(basename "$hook")"
  chmod +x "$hook"
  ln -sf "$SRC_DIR/$name" "$DEST_DIR/$name"
  echo "installed hook: $name -> scripts/git-hooks/$name"
done

echo "Done. Hooks are symlinked, so future edits to scripts/git-hooks/ take effect immediately."
