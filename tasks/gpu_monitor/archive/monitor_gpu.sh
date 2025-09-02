#!/bin/bash

# GPU监控脚本
# 用法: ./monitor_gpu.sh [间隔秒数]

INTERVAL=${1:-2}  # 默认2秒间隔
LOG_FILE="gpu_monitor_$(date +%Y%m%d_%H%M%S).log"

echo "开始GPU监控 - 间隔: ${INTERVAL}秒"
echo "日志文件: $LOG_FILE"
echo "按 Ctrl+C 停止监控"
echo "----------------------------------------"

while true; do
    clear
    echo "=== GPU状态监控 - $(date '+%Y-%m-%d %H:%M:%S') ==="
    echo ""
    
    # 显示GPU基本信息
    echo "📊 GPU基本信息:"
    nvidia-smi --query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu,power.draw --format=csv,noheader,nounits | while IFS=, read -r index name total used free util temp power; do
        echo "GPU $index: $name"
        echo "  显存: ${used}MB / ${total}MB (${free}MB 可用)"
        echo "  利用率: ${util}% | 温度: ${temp}°C | 功耗: ${power}W"
        echo ""
    done
    
    # 显示进程信息
    echo "🔍 当前GPU进程:"
    nvidia-smi --query-compute-apps=pid,process_name,gpu_uuid,used_memory --format=csv,noheader,nounits | while IFS=, read -r pid name uuid mem; do
        if [ ! -z "$pid" ]; then
            echo "  PID $pid: $name (GPU $uuid) - ${mem}MB"
        fi
    done
    
    # 记录到日志文件
    echo "$(date '+%Y-%m-%d %H:%M:%S') - GPU监控" >> "$LOG_FILE"
    nvidia-smi --query-gpu=index,memory.used,utilization.gpu,temperature.gpu --format=csv,noheader,nounits >> "$LOG_FILE"
    
    echo ""
    echo "----------------------------------------"
    echo "日志文件: $LOG_FILE"
    echo "按 Ctrl+C 停止监控"
    
    sleep $INTERVAL
done
