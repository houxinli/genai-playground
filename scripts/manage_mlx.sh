#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="logs"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
LOG_FILE="$LOG_DIR/mlx-$TIMESTAMP.log"
PID_FILE="$LOG_DIR/mlx.pid"
LATEST_LOG="$LOG_DIR/mlx-latest.log"

mkdir -p "$LOG_DIR"

create_latest_link() {
    ln -sf "$LOG_FILE" "$LATEST_LOG"
}

_read_target() {
    if [ -f "$PID_FILE" ]; then
        cat "$PID_FILE"
    fi
}

_target_is_tmux() {
    [[ "${1:-}" == tmux:* ]]
}

_target_is_pid() {
    [[ "${1:-}" == pid:* ]]
}

_target_value() {
    local target=${1:-}
    echo "${target#*:}"
}

_is_running() {
    local target=${1:-}
    if _target_is_tmux "$target"; then
        tmux has-session -t "$(_target_value "$target")" 2>/dev/null
        return $?
    fi
    if _target_is_pid "$target"; then
        kill -0 "$(_target_value "$target")" 2>/dev/null
        return $?
    fi
    return 1
}

_start_fg() {
    echo "📝 日志文件: $LOG_FILE"
    create_latest_link
    script -q -f -c "./scripts/serve_mlx.sh" "$LOG_FILE"
}

_start_bg() {
    echo "📝 日志文件: $LOG_FILE"
    create_latest_link
    if command -v tmux >/dev/null 2>&1; then
        SESSION=${SESSION:-mlx}
        tmux has-session -t "$SESSION" 2>/dev/null && tmux kill-session -t "$SESSION"
        export LOG_FILE
        tmux new-session -d -s "$SESSION" \
            "bash -lc 'script -q -f -c ./scripts/serve_mlx.sh \"$LOG_FILE\"'"
        echo "tmux:$SESSION" > "$PID_FILE"
        echo "✅ 服务已启动，tmux session: $SESSION"
        echo "💡 查看实时进度：tmux attach -t $SESSION  （退出按 Ctrl-b d）"
        return
    fi

    echo "⚠️  未检测到 tmux，回退到 nohup 后台模式"
    if command -v script >/dev/null 2>&1; then
        nohup bash -lc "script -q -f -c ./scripts/serve_mlx.sh \"$LOG_FILE\"" >/dev/null 2>&1 &
    else
        nohup bash -lc "./scripts/serve_mlx.sh >> \"$LOG_FILE\" 2>&1" >/dev/null 2>&1 &
    fi
    BG_PID=$!
    echo "pid:$BG_PID" > "$PID_FILE"
    echo "✅ 服务已启动，PID: $BG_PID"
    echo "💡 查看日志：tail -f $LATEST_LOG"
}

case "${1:-}" in
    run)
        MODE=${MODE:-fg}
        if [ "$MODE" = "bg" ]; then
            if [ -f "$PID_FILE" ]; then
                TARGET=$(_read_target)
                if _is_running "$TARGET"; then
                    echo "⚠️  服务已在后台运行：$TARGET"
                    exit 1
                else
                    rm -f "$PID_FILE"
                fi
            fi
            _start_bg
        else
            if [ -f "$PID_FILE" ]; then
                TARGET=$(_read_target)
                if _is_running "$TARGET"; then
                    echo "⚠️  检测到后台服务 $TARGET，请先执行 ./scripts/manage_mlx.sh stop"
                    exit 1
                else
                    rm -f "$PID_FILE"
                fi
            fi
            _start_fg
        fi
        ;;

    start)
        echo "🚀 启动 MLX 服务（前台运行 + 日志记录）..."
        _start_fg
        ;;

    start-bg)
        echo "🚀 启动 MLX 服务（后台运行）..."
        if [ -f "$PID_FILE" ]; then
            TARGET=$(_read_target)
            if _is_running "$TARGET"; then
                echo "⚠️  服务已在运行：$TARGET"
                exit 1
            fi
        fi
        _start_bg
        ;;

    restart)
        echo "🔄 重启 MLX 服务..."
        if [ -f "$PID_FILE" ]; then
            TARGET=$(_read_target)
            if _target_is_tmux "$TARGET"; then
                tmux kill-session -t "$(_target_value "$TARGET")" || true
                sleep 2
            elif _target_is_pid "$TARGET"; then
                kill "$(_target_value "$TARGET")" 2>/dev/null || true
                sleep 2
            fi
            rm -f "$PID_FILE"
        fi
        MODE=${MODE:-bg}
        if [ "$MODE" = "fg" ]; then
            _start_fg
        else
            _start_bg
        fi
        ;;

    stop)
        echo "🛑 停止 MLX 服务..."
        if [ -f "$PID_FILE" ]; then
            TARGET=$(_read_target)
            if _target_is_tmux "$TARGET" && _is_running "$TARGET"; then
                SESSION_NAME=$(_target_value "$TARGET")
                echo "🛑 停止 tmux session: $SESSION_NAME"
                tmux kill-session -t "$SESSION_NAME" || true
                sleep 2
                rm -f "$PID_FILE"
                echo "✅ 服务已停止"
            elif _target_is_pid "$TARGET" && _is_running "$TARGET"; then
                BG_PID=$(_target_value "$TARGET")
                echo "🛑 停止后台进程: $BG_PID"
                kill "$BG_PID" 2>/dev/null || true
                sleep 2
                rm -f "$PID_FILE"
                echo "✅ 服务已停止"
            else
                echo "⚠️  未发现运行中的后台服务"
                rm -f "$PID_FILE"
            fi
        else
            echo "⚠️  PID 文件不存在"
        fi
        ;;

    status)
        if [ -f "$PID_FILE" ]; then
            TARGET=$(_read_target)
            if _is_running "$TARGET"; then
                echo "✅ 服务正在运行：$TARGET"
                echo "📝 最新日志: $LATEST_LOG"
            else
                echo "❌ 服务未运行（记录的后台目标不存在）"
                rm -f "$PID_FILE"
            fi
        else
            echo "❌ 服务未运行"
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
        ls -la "$LOG_DIR"/mlx-*.log 2>/dev/null | head -10
        echo ""
        echo "📝 查看最新日志的最后几行:"
        if [ -f "$LATEST_LOG" ]; then
            tail -20 "$LATEST_LOG"
        else
            echo "❌ 日志文件不存在"
        fi
        ;;

    *)
        echo "用法: $0 {run|start|start-bg|stop|restart|status|logs|logs-all}"
        echo ""
        echo "可选环境变量:"
        echo "  - MODE=fg/bg  选择前台或后台"
        echo "  - MODEL=...   选择模型，例如 deadbydawn101/gemma-4-E2B-Heretic-Uncensored-mlx-4bit"
        echo "  - PORT=8080   服务端口"
        echo "  - HOST=127.0.0.1 监听地址"
        echo "  - HF_HOME=... 模型缓存目录"
        exit 1
        ;;
esac
