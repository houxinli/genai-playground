#!/usr/bin/env python3
"""
GPU监控工具
实时监控GPU状态，包括显存、利用率、温度、功耗等
"""

import time
import subprocess
import json
import argparse
from datetime import datetime
import os

def get_gpu_info():
    """获取GPU信息"""
    try:
        result = subprocess.run(['nvidia-smi', '--query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu,power.draw', '--format=csv,noheader,nounits'], 
                              capture_output=True, text=True)
        return result.stdout.strip().split('\n')
    except Exception as e:
        print(f"获取GPU信息失败: {e}")
        return []

def get_gpu_processes():
    """获取GPU进程信息"""
    try:
        result = subprocess.run(['nvidia-smi', '--query-compute-apps=pid,process_name,gpu_uuid,used_memory', '--format=csv,noheader,nounits'], 
                              capture_output=True, text=True)
        return result.stdout.strip().split('\n')
    except Exception as e:
        print(f"获取GPU进程信息失败: {e}")
        return []

def format_size(mb):
    """格式化显存大小"""
    if mb >= 1024:
        return f"{mb/1024:.1f}GB"
    return f"{mb}MB"

def monitor_gpu(interval=2, log_file=None):
    """持续监控GPU"""
    print(f"🚀 开始GPU监控 - 间隔: {interval}秒")
    if log_file:
        print(f"📝 日志文件: {log_file}")
    print("按 Ctrl+C 停止监控")
    print("=" * 60)
    
    while True:
        try:
            # 清屏
            os.system('clear' if os.name == 'posix' else 'cls')
            
            # 显示时间
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"🕐 GPU状态监控 - {current_time}")
            print()
            
            # 获取GPU信息
            gpu_info = get_gpu_info()
            if gpu_info:
                print("📊 GPU状态:")
                for line in gpu_info:
                    if line.strip():
                        parts = line.split(', ')
                        if len(parts) >= 8:
                            index, name, total, used, free, util, temp, power = parts
                            print(f"  GPU {index}: {name}")
                            print(f"    显存: {format_size(int(used))} / {format_size(int(total))} ({format_size(int(free))} 可用)")
                            print(f"    利用率: {util}% | 温度: {temp}°C | 功耗: {power}W")
                            print()
            
            # 获取进程信息
            processes = get_gpu_processes()
            if processes:
                print("🔍 GPU进程:")
                for line in processes:
                    if line.strip():
                        parts = line.split(', ')
                        if len(parts) >= 4:
                            pid, name, uuid, mem = parts
                            if pid.strip():
                                print(f"  PID {pid}: {name} - {format_size(int(mem))}")
                print()
            
            # 记录到日志文件
            if log_file:
                with open(log_file, 'a', encoding='utf-8') as f:
                    f.write(f"{current_time} - GPU监控\n")
                    for line in gpu_info:
                        if line.strip():
                            f.write(f"{line}\n")
                    f.write("\n")
            
            print("=" * 60)
            print(f"日志文件: {log_file}" if log_file else "无日志记录")
            print("按 Ctrl+C 停止监控")
            
            time.sleep(interval)
            
        except KeyboardInterrupt:
            print("\n\n🛑 监控已停止")
            break
        except Exception as e:
            print(f"❌ 监控出错: {e}")
            time.sleep(interval)

def main():
    parser = argparse.ArgumentParser(description='GPU监控工具')
    parser.add_argument('-i', '--interval', type=int, default=2, help='监控间隔（秒）')
    parser.add_argument('-l', '--log', help='日志文件路径')
    
    args = parser.parse_args()
    
    # 生成默认日志文件名
    if not args.log:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        args.log = f"gpu_monitor_{timestamp}.log"
    
    monitor_gpu(args.interval, args.log)

if __name__ == "__main__":
    main()
