#!/usr/bin/env bash
set -euo pipefail

# 翻译进度监控脚本

LOG_DIR="tasks/translation/logs"
LATEST_LOG="$LOG_DIR/latest_translation.log"

# 检查翻译任务是否运行
check_translation_status() {
    if [ -f "$LOG_DIR/translation.pid" ]; then
        SESSION=$(cat "$LOG_DIR/translation.pid")
        if tmux has-session -t "$SESSION" 2>/dev/null; then
            return 0  # 运行中
        else
            return 1  # 未运行
        fi
    else
        return 1  # 未运行
    fi
}

# 显示翻译进度
show_progress() {
    if [ -f "$LATEST_LOG" ]; then
        echo "📊 翻译进度监控 (最后10行):"
        echo "----------------------------------------"
        tail -10 "$LATEST_LOG"
        echo "----------------------------------------"
    else
        echo "❌ 翻译日志文件不存在"
    fi
}

# 实时监控
monitor_realtime() {
    if [ -f "$LATEST_LOG" ]; then
        echo "🔍 实时监控翻译进度 (Ctrl+C 退出):"
        echo "----------------------------------------"
        tail -f "$LATEST_LOG"
    else
        echo "❌ 翻译日志文件不存在"
    fi
}

# 显示统计信息
show_stats() {
    if [ -f "$LATEST_LOG" ]; then
        echo "📈 翻译统计信息:"
        echo "----------------------------------------"
        
        # 统计翻译批次
        local batches=$(grep -c "翻译批次" "$LATEST_LOG" 2>/dev/null || echo "0")
        echo "翻译批次数: $batches"
        
        # 统计成功/失败
        local success=$(grep -c "批次翻译成功" "$LATEST_LOG" 2>/dev/null || echo "0")
        local failed=$(grep -c "批次翻译失败" "$LATEST_LOG" 2>/dev/null || echo "0")
        echo "成功批次数: $success"
        echo "失败批次数: $failed"
        
        # 统计QC结果
        local qc_pass=$(grep -c "QC通过" "$LATEST_LOG" 2>/dev/null || echo "0")
        local qc_fail=$(grep -c "QC失败" "$LATEST_LOG" 2>/dev/null || echo "0")
        echo "QC通过次数: $qc_pass"
        echo "QC失败次数: $qc_fail"
        
        # 统计Token使用
        local total_tokens=$(grep "Token使用" "$LATEST_LOG" | grep -o "total_tokens=[0-9]*" | cut -d= -f2 | awk '{sum+=$1} END {print sum+0}')
        echo "总Token使用: $total_tokens"
        
        echo "----------------------------------------"
    else
        echo "❌ 翻译日志文件不存在"
    fi
}

# 主逻辑
case "${1:-}" in
    status)
        if check_translation_status; then
            echo "✅ 翻译任务正在运行"
            show_progress
        else
            echo "❌ 翻译任务未运行"
        fi
        ;;
        
    monitor)
        if check_translation_status; then
            monitor_realtime
        else
            echo "❌ 翻译任务未运行，无法监控"
        fi
        ;;
        
    stats)
        show_stats
        ;;
        
    progress)
        show_progress
        ;;
        
    *)
        echo "用法: $0 {status|monitor|stats|progress}"
        echo ""
        echo "命令说明:"
        echo "  status    - 查看翻译任务状态和最新进度"
        echo "  monitor   - 实时监控翻译进度"
        echo "  stats     - 显示翻译统计信息"
        echo "  progress  - 显示最新进度（最后10行）"
        echo ""
        echo "示例:"
        echo "  $0 status    # 查看当前状态"
        echo "  $0 monitor   # 实时监控"
        echo "  $0 stats     # 查看统计"
        ;;
esac