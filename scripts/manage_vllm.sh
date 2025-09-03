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

case "${1:-}" in
    start)
        echo "🚀 启动 vLLM 服务（前台运行 + 日志记录）..."
        if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
            echo "⚠️  服务已在运行，PID: $(cat "$PID_FILE")"
            exit 1
        fi
        
        echo "📝 日志文件: $LOG_FILE"
        create_latest_link
        # 前台运行，同时记录日志
        ./scripts/serve_vllm.sh 2>&1 | tee "$LOG_FILE"
        ;;
        
    start-bg)
        echo "🚀 启动 vLLM 服务（后台运行）..."
        if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
            echo "⚠️  服务已在运行，PID: $(cat "$PID_FILE")"
            exit 1
        fi
        
        echo "📝 日志文件: $LOG_FILE"
        create_latest_link
        # 后台运行
        ./scripts/serve_vllm.sh > "$LOG_FILE" 2>&1 &
        echo $! > "$PID_FILE"
        echo "✅ 服务已启动，PID: $(cat "$PID_FILE")"
        ;;
        
    restart)
        echo "🔄 重启 vLLM 服务..."
        if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
            echo "🛑 停止当前服务..."
            kill "$(cat "$PID_FILE")"
            rm -f "$PID_FILE"
            echo "⏳ 等待服务完全停止..."
            sleep 3
        fi
        
        echo "🚀 启动新服务..."
        echo "📝 日志文件: $LOG_FILE"
        create_latest_link
        ./scripts/serve_vllm.sh > "$LOG_FILE" 2>&1 &
        echo $! > "$PID_FILE"
        echo "✅ 服务已重启，PID: $(cat "$PID_FILE")"
        ;;
        
    stop)
        echo "🛑 停止 vLLM 服务..."
        if [ -f "$PID_FILE" ]; then
            PID=$(cat "$PID_FILE")
            if kill -0 "$PID" 2>/dev/null; then
                kill "$PID"
                rm -f "$PID_FILE"
                echo "✅ 服务已停止"
            else
                echo "⚠️  服务未运行"
                rm -f "$PID_FILE"
            fi
        else
            echo "⚠️  PID 文件不存在"
        fi
        ;;
        
    status)
        if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
            echo "✅ 服务正在运行，PID: $(cat "$PID_FILE")"
            echo "📝 最新日志: $LATEST_LOG"
            echo "📝 当前日志: $LOG_FILE"
        else
            echo "❌ 服务未运行"
            [ -f "$PID_FILE" ] && rm -f "$PID_FILE"
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
        echo "用法: $0 {start|start-bg|stop|restart|status|logs|logs-all|clean-logs|test}"
        echo ""
        echo "命令说明:"
        echo "  start      - 前台启动 vLLM 服务（同时记录日志）"
        echo "  start-bg   - 后台启动 vLLM 服务"
        echo "  stop       - 停止 vLLM 服务"
        echo "  restart    - 重启 vLLM 服务"
        echo "  status     - 查看服务状态"
        echo "  logs       - 实时查看最新日志"
        echo "  logs-all   - 查看所有日志文件"
        echo "  clean-logs - 清理7天前的旧日志"
        echo "  test       - 测试翻译功能"
        echo ""
        echo "日志文件:"
        echo "  - 时间戳日志: logs/vllm-YYYYMMDD-HHMMSS.log"
        echo "  - 最新日志链接: logs/latest.log"
        exit 1
        ;;
esac
