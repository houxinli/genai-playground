# GPU监控工具使用指南

## 🚀 快速开始

### 方法1: 使用 watch 命令（最简单）
```bash
# 每1秒刷新一次
watch -n 1 nvidia-smi

# 每2秒刷新一次
watch -n 2 nvidia-smi
```

### 方法2: 使用 nvidia-smi dmon（轻量级）
```bash
# 每2秒输出一次，显示关键指标
nvidia-smi dmon -s pucvmet -d 2

# 参数说明:
# -s pucvmet: 显示 power, utilization, compute mode, voltage, memory, temperature
# -d 2: 每2秒输出一次
```

### 方法3: 使用我们的监控脚本

#### Bash脚本版本
```bash
# 使用默认2秒间隔
./scripts/monitor_gpu.sh

# 自定义间隔（比如5秒）
./scripts/monitor_gpu.sh 5
```

#### Python脚本版本（推荐）
```bash
# 使用默认设置
python scripts/gpu_monitor.py

# 自定义间隔和日志文件
python scripts/gpu_monitor.py -i 3 -l my_gpu_log.txt

# 参数说明:
# -i, --interval: 监控间隔（秒）
# -l, --log: 日志文件路径
```

## 📊 监控内容

### 基本信息
- GPU型号和索引
- 显存使用情况（已用/总量/可用）
- GPU利用率
- 温度
- 功耗

### 进程信息
- 正在使用GPU的进程PID
- 进程名称
- 每个进程占用的显存

### 日志记录
- 自动记录监控数据到日志文件
- 便于后续分析和调试

## 🛑 停止监控

所有监控方法都可以通过 `Ctrl+C` 停止。

## 💡 使用建议

1. **日常监控**: 使用 `watch -n 1 nvidia-smi` 最简单
2. **详细分析**: 使用 Python 脚本，功能最全面
3. **长期记录**: 使用带日志功能的脚本
4. **轻量监控**: 使用 `nvidia-smi dmon` 减少屏幕刷新

## 🔧 自定义配置

可以修改脚本中的参数来适应不同需求：
- 调整监控间隔
- 修改显示格式
- 添加告警阈值
- 集成到其他监控系统
