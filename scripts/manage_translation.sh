#!/usr/bin/env bash
set -euo pipefail

# 翻译任务管理脚本 - 支持前台/后台模式

# 配置
LOG_DIR="tasks/translation/logs"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
LOG_FILE="$LOG_DIR/translation-$TIMESTAMP.log"
PID_FILE="$LOG_DIR/translation.pid"
LATEST_LOG="$LOG_DIR/latest_translation.log"

# 创建日志目录
mkdir -p "$LOG_DIR"

# 创建最新日志的符号链接
create_latest_link() {
    ln -sf "$LOG_FILE" "$LATEST_LOG"
}

run_with_script_log() {
    local cmd="$1"
    local log_file="$2"
    # GNU script: script -q -f -c "<cmd>" <log>
    # BSD/macOS script: script -qF <log> <cmd> [args...]
    if script --version >/dev/null 2>&1; then
        script -q -f -c "$cmd" "$log_file"
    else
        script -qF "$log_file" bash -lc "$cmd"
    fi
}

build_translate_cmd() {
    local translate_bin="$1"
    shift
    local escaped_args=()
    local arg
    for arg in "$@"; do
        escaped_args+=("$(printf '%q' "$arg")")
    done
    local escaped_bin
    escaped_bin="$(printf '%q' "$translate_bin")"
    if [ ${#escaped_args[@]} -eq 0 ]; then
        printf '%s' "$escaped_bin"
    else
        printf '%s %s' "$escaped_bin" "${escaped_args[*]}"
    fi
}

# 前台运行翻译任务
_start_fg() {
    echo "📝 翻译日志文件: $LOG_FILE"
    create_latest_link
    
    # 构建翻译命令
    local translate_cmd
    translate_cmd="$(build_translate_cmd "./tasks/translation/translate" "$@")"
    echo "🚀 执行翻译命令: $translate_cmd"
    
    # 使用script记录日志并实时显示
    run_with_script_log "$translate_cmd" "$LOG_FILE"
}

# 后台运行翻译任务
_start_bg() {
    echo "📝 翻译日志文件: $LOG_FILE"
    create_latest_link
    
    SESSION=${SESSION:-translation}
    
    # 检查是否已有会话
    if tmux has-session -t "$SESSION" 2>/dev/null; then
        echo "⚠️  翻译任务已在后台运行，session: $SESSION"
        echo "💡 查看进度：tmux attach -t $SESSION"
        exit 1
    fi
    
    # 构建翻译命令（使用绝对路径）
    local translate_bin
    translate_bin="$(cd "$(dirname "$0")/../tasks/translation" && pwd)/translate"
    local translate_cmd
    translate_cmd="$(build_translate_cmd "$translate_bin" "$@")"
    echo "🚀 后台执行翻译命令: $translate_cmd"
    
    # 在tmux中运行翻译任务（使用vllm的成功模式）
    export LOG_FILE
    tmux new-session -d -s "$SESSION" \
        "bash -lc 'if script --version >/dev/null 2>&1; then script -q -f -c \"$translate_cmd\" \"$LOG_FILE\"; else script -qF \"$LOG_FILE\" bash -lc \"$translate_cmd\"; fi'"
    
    echo "$SESSION" > "$PID_FILE"
    echo "✅ 翻译任务已启动，tmux session: $SESSION"
    echo "💡 查看实时进度：tmux attach -t $SESSION  （退出按 Ctrl-b d）"
    echo "💡 查看日志：tail -f $LATEST_LOG"
}

# 停止翻译任务
_stop() {
    if [ -f "$PID_FILE" ]; then
        SESSION=$(cat "$PID_FILE")
        if tmux has-session -t "$SESSION" 2>/dev/null; then
            echo "🛑 停止翻译任务，session: $SESSION"
            tmux kill-session -t "$SESSION"
            rm -f "$PID_FILE"
            echo "✅ 翻译任务已停止"
        else
            echo "❌ 翻译任务未运行"
            rm -f "$PID_FILE"
        fi
    else
        echo "❌ 翻译任务未运行"
    fi
}

# 查看状态
_status() {
    if [ -f "$PID_FILE" ]; then
        SESSION=$(cat "$PID_FILE")
        if tmux has-session -t "$SESSION" 2>/dev/null; then
            echo "✅ 翻译任务正在运行，session: $SESSION"
            echo "💡 查看进度：tmux attach -t $SESSION"
            echo "💡 查看日志：tail -f $LATEST_LOG"
        else
            echo "❌ 翻译任务未运行（PID文件存在但会话不存在）"
            rm -f "$PID_FILE"
        fi
    else
        echo "❌ 翻译任务未运行"
    fi
}

# 查看日志
_logs() {
    if [ -f "$LATEST_LOG" ]; then
        echo "📝 翻译任务日志 (最后20行):"
        tail -20 "$LATEST_LOG"
    else
        echo "❌ 日志文件不存在"
    fi
}

# 实时查看日志
_logs_follow() {
    if [ -f "$LATEST_LOG" ]; then
        echo "📝 实时查看翻译任务日志 (Ctrl+C 退出):"
        tail -f "$LATEST_LOG"
    else
        echo "❌ 日志文件不存在"
    fi
}

# 批量翻译
_batch_translate() {
    local mode="$1"
    shift
    
    # 检查参数
    if [ $# -eq 0 ]; then
        echo "❌ 请指定输入目录或文件"
        echo "用法: $0 batch [fg|bg] <输入目录或文件> [翻译参数...]"
        echo "示例: $0 batch-bg tasks/translation/data/pixiv/50235390 --bilingual-simple --stream"
        exit 1
    fi
    
    local input_path="$1"
    shift
    
    # 构建批量翻译命令
    local batch_cmd
    batch_cmd="$(build_translate_cmd "./tasks/translation/translate" "$input_path" "$@")"
    
    echo "🚀 批量翻译命令: $batch_cmd"
    echo "📁 输入路径: $input_path"
    echo "🔍 将自动跳过已翻译文件"
    
    if [ "$mode" = "bg" ]; then
        _start_bg "$input_path" "$@"
    else
        _start_fg "$input_path" "$@"
    fi
}

# 主逻辑
case "${1:-}" in
    batch)
        MODE=${MODE:-fg}
        shift  # 移除第一个参数
        _batch_translate "$MODE" "$@"
        ;;
        
    batch-fg)
        shift  # 移除第一个参数
        _batch_translate "fg" "$@"
        ;;
        
    batch-bg)
        shift  # 移除第一个参数
        _batch_translate "bg" "$@"
        ;;
    start)
        MODE=${MODE:-fg}
        shift  # 移除第一个参数
        if [ "$MODE" = "bg" ]; then
            _start_bg "$@"
        else
            _start_fg "$@"
        fi
        ;;
        
    start-fg)
        shift  # 移除第一个参数
        _start_fg "$@"
        ;;
        
    start-bg)
        shift  # 移除第一个参数
        _start_bg "$@"
        ;;
        
    stop)
        _stop
        ;;
        
    status)
        _status
        ;;
        
    logs)
        _logs
        ;;
        
    logs-follow)
        _logs_follow
        ;;
        
    attach)
        if [ -f "$PID_FILE" ]; then
            SESSION=$(cat "$PID_FILE")
            if tmux has-session -t "$SESSION" 2>/dev/null; then
                echo "🔗 连接到翻译任务会话..."
                tmux attach -t "$SESSION"
            else
                echo "❌ 翻译任务会话不存在"
            fi
        else
            echo "❌ 翻译任务未运行"
        fi
        ;;
        
    *)
        echo "用法: $0 {start|start-fg|start-bg|batch|batch-fg|batch-bg|stop|status|logs|logs-follow|attach} [参数...]"
        echo ""
        echo "单文件翻译:"
        echo "  start         - 根据 MODE=fg/bg 启动翻译任务（默认 fg）"
        echo "  start-fg      - 前台启动翻译任务（实时显示进度）"
        echo "  start-bg      - 后台启动翻译任务（tmux会话，SSH断开不影响）"
        echo ""
        echo "批量翻译（自动跳过已翻译文件）:"
        echo "  batch         - 根据 MODE=fg/bg 批量翻译（默认 fg）"
        echo "  batch-fg      - 前台批量翻译（实时显示进度）"
        echo "  batch-bg      - 后台批量翻译（tmux会话，SSH断开不影响）"
        echo ""
        echo "任务管理:"
        echo "  stop          - 停止翻译任务"
        echo "  status        - 查看翻译任务状态"
        echo "  logs          - 查看翻译任务日志（最后20行）"
        echo "  logs-follow   - 实时查看翻译任务日志"
        echo "  attach        - 连接到翻译任务会话"
        echo ""
        echo "单文件翻译示例:"
        echo "  $0 start-fg tasks/translation/data/pixiv/50235390/25341719.txt --bilingual-simple --stream"
        echo "  $0 start-bg tasks/translation/data/pixiv/50235390/25341719.txt --bilingual-simple --stream"
        echo ""
        echo "批量翻译示例:"
        echo "  $0 batch-fg tasks/translation/data/pixiv/50235390 --bilingual-simple --stream"
        echo "  $0 batch-bg tasks/translation/data/pixiv/50235390 --bilingual-simple --stream"
        echo "  MODE=bg $0 batch tasks/translation/data/pixiv/50235390 --bilingual-simple --stream"
        echo ""
        echo "后台模式使用技巧:"
        echo "  1. 启动后台任务: $0 batch-bg [目录] [参数]"
        echo "  2. 查看实时进度: $0 attach 或 tmux attach -t translation"
        echo "  3. 退出tmux会话: Ctrl-b d (任务继续运行)"
        echo "  4. 查看日志: $0 logs-follow"
        echo "  5. 停止任务: $0 stop"
        echo ""
        echo "批量翻译特性:"
        echo "  ✅ 自动跳过已翻译的 _zh.txt 文件"
        echo "  ✅ 自动跳过高质量的 _bilingual.txt 文件"
        echo "  ✅ 自动清理低质量的翻译文件"
        echo "  ✅ 支持目录和文件列表输入"
        ;;
esac
