#!/usr/bin/env bash
set -euo pipefail

# 简介：从白名单中匹配命令（字符串前缀匹配），匹配成功才执行；
# 全量输出到日志，便于审计与回放。

BASE_DIR="$(cd "$(dirname "$0")"/.. && pwd)"
ALLOWLIST_FILE="${BASE_DIR}/scripts/allowlist.txt"
LOG_DIR="${BASE_DIR}/logs"
LOG_FILE="${LOG_DIR}/run_safe.log"

mkdir -p "$LOG_DIR"

if [[ $# -lt 1 ]]; then
	echo "Usage: run_safe.sh <command...>" >&2
	exit 2
fi

CMD_STR="$*"

if [[ ! -f "$ALLOWLIST_FILE" ]]; then
	echo "[run_safe] allowlist not found: $ALLOWLIST_FILE" >&2
	exit 3
fi

allowed=false
while IFS= read -r line; do
	# 跳过空行与注释
	[[ -z "${line}" || "${line}" =~ ^# ]] && continue
	# 前缀匹配：以白名单行作为前缀
	if [[ "$CMD_STR" == "$line"* ]]; then
		allowed=true
		break
	fi
done <"$ALLOWLIST_FILE"

ts="$(date '+%Y-%m-%d %H:%M:%S')"

if ! $allowed; then
	echo "[$ts][DENY] $CMD_STR" | tee -a "$LOG_FILE" >&2
	echo "[run_safe] command is not in allowlist. Abort." >&2
	exit 4
fi

echo "[$ts][ALLOW] $CMD_STR" | tee -a "$LOG_FILE"
set -x
eval "$CMD_STR" 2>&1 | tee -a "$LOG_FILE"
set +x


