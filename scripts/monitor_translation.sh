#!/usr/bin/env bash
set -euo pipefail

# 监听翻译进度的脚本
# 用法: ./scripts/monitor_translation.sh [log_dir]

LOG_DIR=${1:-"tasks/translation/logs"}

echo "🔍 开始监听翻译进度..."
echo "📁 监听目录: $LOG_DIR"
echo "⏰ 开始时间: $(date)"
echo "=" * 50

# 使用 tail -f 监听所有日志文件
if command -v multitail >/dev/null 2>&1; then
    # 如果有 multitail，使用它来同时监听多个文件
    echo "使用 multitail 监听多个日志文件..."
    multitail -e "translation" "$LOG_DIR"/*.log
else
    # 否则使用 tail -f 监听最新的日志文件
    echo "使用 tail -f 监听最新日志文件..."
    echo "按 Ctrl+C 停止监听"
    echo ""
    
    # 找到最新的日志文件
    LATEST_LOG=$(find "$LOG_DIR" -name "translation_*.log" -type f -printf '%T@ %p\n' | sort -n | tail -1 | cut -d' ' -f2-)
    
    if [ -n "$LATEST_LOG" ]; then
        echo "📄 监听文件: $LATEST_LOG"
        echo ""
        tail -f "$LATEST_LOG"
    else
        echo "❌ 未找到日志文件"
        echo "💡 提示: 请先运行翻译命令"
    fi
fi
