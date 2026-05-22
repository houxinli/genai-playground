#!/usr/bin/env bash
# Symlink the version-controlled git hooks in scripts/git-hooks/ into .git/hooks/.
# Re-run safely any time; it overwrites existing symlinks.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
SRC_DIR="$REPO_ROOT/scripts/git-hooks"
DEST_DIR="$REPO_ROOT/.git/hooks"

if [ ! -d "$SRC_DIR" ]; then
  echo "No hooks directory at $SRC_DIR" >&2
  exit 1
fi

mkdir -p "$DEST_DIR"
for hook in "$SRC_DIR"/*; do
  name="$(basename "$hook")"
  chmod +x "$hook"
  ln -sf "../../scripts/git-hooks/$name" "$DEST_DIR/$name"
  echo "installed hook: $name -> scripts/git-hooks/$name"
done

echo "Done. Hooks are symlinked, so future edits to scripts/git-hooks/ take effect immediately."
