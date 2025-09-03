#!/usr/bin/env bash
set -euo pipefail

# vLLM 服务管理脚本 - 带时间戳日志

LOG_DIR="logs"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
LOG_FILE="$LOG_DIR/vllm-$TIMESTAMP.log"
PID_FILE="$LOG_DIR/vllm.pid"
LATEST_LOG="$LOG_DIR/latest.log"

# 创建日志目录
mkdir -p "$LOG_DIR"

# 创建最新日志的符号链接
create_latest_link() {
    ln -sf "$LOG_FILE" "$LATEST_LOG"
}

# 启动（前台）
_start_fg() {
    echo "📝 日志文件: $LOG_FILE"
    create_latest_link
    script -q -f -c "./scripts/serve_vllm.sh" "$LOG_FILE"
}

# 启动（后台 tmux）
_start_bg() {
    echo "📝 日志文件: $LOG_FILE"
    create_latest_link
    SESSION=${SESSION:-vllm}
    tmux has-session -t "$SESSION" 2>/dev/null && tmux kill-session -t "$SESSION"
    export LOG_FILE
    tmux new-session -d -s "$SESSION" \
        "script -q -f -c 'bash -lc ./scripts/serve_vllm.sh' \"$LOG_FILE\""
    echo "$SESSION" > "$PID_FILE"
    echo "✅ 服务已启动，tmux session: $SESSION"
    echo "💡 查看实时进度：tmux attach -t $SESSION  （退出按 Ctrl-b d）"
}

# 等待显存释放，超时退出（秒）
_wait_gpu_free() {
    local timeout_sec=${1:-30}
    local threshold_mb=${2:-1000}
    command -v nvidia-smi >/dev/null 2>&1 || return 0
    local waited=0
    while true; do
        local used_list
        used_list=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null || echo "")
        if [ -z "$used_list" ]; then
            break
        fi
        local over
        over=$(echo "$used_list" | awk -v th=$threshold_mb '$1>th{c++} END{print c+0}')
        if [ "$over" -eq 0 ]; then
            break
        fi
        if [ "$waited" -ge "$timeout_sec" ]; then
            echo "⚠️  显存仍未完全释放（超过 ${threshold_mb}MiB），继续启动..."
            break
        fi
        sleep 2
        waited=$((waited+2))
    done
}

case "${1:-}" in
    run)
        MODE=${MODE:-fg}
        if [ "$MODE" = "bg" ]; then
            # 检查已运行的 tmux 会话
            if [ -f "$PID_FILE" ]; then
                S=$(cat "$PID_FILE")
                if tmux has-session -t "$S" 2>/dev/null; then
                    echo "⚠️  服务已在后台运行，session: $S"
                    exit 1
                else
                    rm -f "$PID_FILE"
                fi
            fi
            _start_bg
        else
            # 前台运行前确保无后台会话
            if [ -f "$PID_FILE" ]; then
                S=$(cat "$PID_FILE")
                if tmux has-session -t "$S" 2>/dev/null; then
                    echo "⚠️  检测到后台会话 $S，请先执行 ./scripts/manage_vllm.sh stop"
                    exit 1
                else
                    rm -f "$PID_FILE"
                fi
            fi
            _start_fg
        fi
        ;;

    start)
        echo "🚀 启动 vLLM 服务（前台运行 + 日志记录）..."
        # 如果后台 tmux 会话存在，则阻止前台启动
        if [ -f "$PID_FILE" ]; then
            SESSION_NAME=$(cat "$PID_FILE")
            if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
                echo "⚠️  后台服务已在运行，session: $SESSION_NAME"
                exit 1
            else
                rm -f "$PID_FILE"
            fi
        fi
        _start_fg
        ;;
        
    start-bg)
        echo "🚀 启动 vLLM 服务（后台运行）..."
        if [ -f "$PID_FILE" ]; then
            SESSION_NAME=$(cat "$PID_FILE")
            if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
                echo "⚠️  服务已在运行，session: $SESSION_NAME"
                exit 1
            fi
        fi
        _start_bg
        ;;

        
    restart)
        echo "🔄 重启 vLLM 服务..."
        # 若存在已记录的会话，先尝试停止
        if [ -f "$PID_FILE" ]; then
            SESSION_NAME=$(cat "$PID_FILE")
            if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
                echo "🛑 停止当前服务 session: $SESSION_NAME..."
                tmux kill-session -t "$SESSION_NAME" || true
                sleep 2
            fi
            rm -f "$PID_FILE"
        fi

        echo "🔍 检查并清理 GPU 计算进程..."
        VLLM_PIDS=$(nvidia-smi --query-compute-apps=pid --format=csv,noheader,nounits 2>/dev/null | grep -v "No running" | tr '\n' ' ' || true)
        if [ -n "${VLLM_PIDS:-}" ]; then
            echo "⚠️  发现残留进程: $VLLM_PIDS，强制终止..."
            kill -9 $VLLM_PIDS 2>/dev/null || true
        fi
        echo "⏳ 等待显存完全释放..."
        _wait_gpu_free 40 800

        echo "🚀 启动新服务..."
        MODE=${MODE:-bg}
        if [ "$MODE" = "fg" ]; then
            _start_fg
        else
            _start_bg
        fi
        ;;
        
    stop)
        echo "🛑 停止 vLLM 服务..."
        if [ -f "$PID_FILE" ]; then
            SESSION_NAME=$(cat "$PID_FILE")
            if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
                echo "🛑 停止 tmux session: $SESSION_NAME"
                tmux kill-session -t "$SESSION_NAME" || true
                sleep 2
                rm -f "$PID_FILE"
                echo "✅ 服务已停止"
            else
                echo "⚠️  未发现运行中的 tmux 会话"
                rm -f "$PID_FILE"
            fi
        else
            echo "⚠️  PID 文件不存在"
        fi
        ;;
        
    status)
        if [ -f "$PID_FILE" ]; then
            SESSION_NAME=$(cat "$PID_FILE")
            if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
                echo "✅ 服务正在运行，session: $SESSION_NAME"
                echo "📝 最新日志: $LATEST_LOG"
                echo "📝 当前日志: $LOG_FILE"
            else
                echo "❌ 服务未运行（记录的 session 不存在）"
                rm -f "$PID_FILE"
            fi
        else
            echo "❌ 服务未运行"
        fi
        ;;
        
    logs-requests)
        if [ -f "$LATEST_LOG" ]; then
            echo "📝 查看请求日志: $LATEST_LOG"
            echo "🔍 过滤包含 'request' 或 'completion' 的日志行..."
            tail -f "$LATEST_LOG" | grep -E "(request|completion|generation|token|latency)"
        else
            echo "❌ 日志文件不存在"
        fi
        ;;
        
    logs)
        if [ -f "$LATEST_LOG" ]; then
            echo "📝 查看最新日志: $LATEST_LOG"
            tail -f "$LATEST_LOG"
        else
            echo "❌ 日志文件不存在"
        fi
        ;;
        
    logs-all)
        echo "📝 查看所有日志文件:"
        ls -la "$LOG_DIR"/vllm-*.log 2>/dev/null | head -10
        echo ""
        echo "📝 查看最新日志的最后几行:"
        if [ -f "$LATEST_LOG" ]; then
            tail -20 "$LATEST_LOG"
        else
            echo "❌ 日志文件不存在"
        fi
        ;;
        
    clean-logs)
        echo "🧹 清理旧日志文件..."
        find "$LOG_DIR" -name "vllm-*.log" -mtime +7 -delete
        echo "✅ 已清理7天前的日志文件"
        ;;
        
    test)
        echo "🧪 测试翻译功能..."
        python tasks/translation/scripts/test_translation.py
        ;;
        
    *)
        echo "用法: $0 {run|start|start-bg|stop|restart|status|logs|logs-requests|logs-all|clean-logs|test}"
        echo ""
        echo "命令说明:"
        echo "  run           - 根据 MODE=fg/bg 启动服务（默认 fg）"
        echo "  start         - 前台启动 vLLM 服务（同时记录日志）"
        echo "  start-bg      - 后台启动 vLLM 服务（tmux+script 保留进度条）"
        echo "  stop          - 停止 vLLM 服务（基于 tmux session）"
        echo "  restart       - 重启 vLLM 服务（MODE=fg/bg，默认 bg）"
        echo "  status        - 查看服务状态（基于 tmux session）"
        echo "  logs           - 实时查看最新日志"
        echo "  logs-requests  - 实时查看请求相关日志（过滤）"
        echo "  logs-all      - 查看所有日志文件"
        echo "  clean-logs    - 清理7天前的旧日志"
        echo "  test          - 测试翻译功能"
        echo ""
        echo "日志文件:"
        echo "  - 时间戳日志: logs/vllm-YYYYMMDD-HHMMSS.log"
        echo "  - 最新日志链接: logs/latest.log"
        echo ""
        echo "可选环境变量:"
        echo "  - MODE=fg/bg  选择前台或后台"
        echo "  - DEBUG=1     开启更详细日志（传递给 serve_vllm.sh）"
        echo "  - MODEL=...   选择模型，例如 Qwen/Qwen3-32B 或 Qwen/Qwen3-32B-AWQ"
        exit 1
        ;;
esac
