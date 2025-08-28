import os
import json
import torch


def collect_gpu_info() -> dict:
	info: dict = {
		"torch_version": torch.__version__,
		"cuda_version": torch.version.cuda,
		"cuda_available": torch.cuda.is_available(),
		"device_count": torch.cuda.device_count(),
		"devices": [],
	}
	for i in range(torch.cuda.device_count()):
		info["devices"].append({
			"index": i,
			"name": torch.cuda.get_device_name(i),
			"capability": torch.cuda.get_device_capability(i),
		})
	return info


def main() -> None:
	info = collect_gpu_info()
	print(json.dumps(info, indent=2, ensure_ascii=False))
	# 生成简要断言
	assert info["cuda_available"], "CUDA 未启用，请检查驱动/容器/CUDA 运行时"
	assert info["device_count"] >= 1, "未检测到 GPU"


if __name__ == "__main__":
	main()


