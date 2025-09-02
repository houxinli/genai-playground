# GPU监控命令总结

## 🎯 推荐命令

### 1. gpustat (最推荐)
```bash
# 持续监控，每1秒刷新
gpustat -i 1

# 持续监控，每2秒刷新
gpustat -i 2
```

### 2. nvidia-smi (原生工具)
```bash
# 持续监控，每1秒刷新
nvidia-smi -l 1

# 持续监控，每2秒刷新
nvidia-smi -l 2
```

### 3. watch + nvidia-smi (通用方法)
```bash
# 每1秒刷新
watch -n 1 nvidia-smi

# 每2秒刷新
watch -n 2 nvidia-smi
```

## 📊 命令对比

| 命令 | 优点 | 缺点 | 推荐度 |
|------|------|------|--------|
| `gpustat -i 1` | 显示简洁、信息全面、易读 | 需要安装gpustat | ⭐⭐⭐⭐⭐ |
| `nvidia-smi -l 1` | 原生工具、无需安装 | 信息较详细、占用空间大 | ⭐⭐⭐⭐ |
| `watch -n 1 nvidia-smi` | 通用性强 | 需要额外命令、资源占用多 | ⭐⭐⭐ |

## 🚀 快速使用

```bash
# 最简单的方式
gpustat -i 1

# 停止监控
Ctrl+C
```

## 📝 归档说明

本文件夹下的其他脚本已归档，因为 `gpustat -i` 已经足够满足日常GPU监控需求。

