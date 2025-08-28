import os
import sys
import json
import site
import shutil
import subprocess


def run(cmd: str) -> str:
	res = subprocess.run(["bash", "-lc", cmd], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
	return res.stdout.strip()


def main() -> None:
	# 基本信息
	info = {
		"python": sys.version,
		"prefix": sys.prefix,
		"site_packages": [],
	}
	try:
		info["site_packages"] = site.getsitepackages()
	except Exception:
		# 一些发行版可能无 getsitepackages
		info["site_packages"] = [site.getusersitepackages()]

	print("[env]")
	print(json.dumps(info, ensure_ascii=False, indent=2))

	# vLLM 版本
	print("\n[vllm]")
	print(run("python -m pip show vllm || true"))

	# site-packages 体积统计
	sp = next((p for p in info["site_packages"] if p.endswith("site-packages")), info["site_packages"][0])
	print(f"\n[site-packages total] {sp}")
	print(run(f"du -sh {sp} | cat"))
	print("\n[top 30 entries in site-packages by size]")
	print(run(f"du -sh {sp}/* | sort -h | tail -n 30 | cat"))

	# conda 环境总体体积
	print("\n[conda env total]")
	print(run("du -sh $CONDA_PREFIX 2>/dev/null || du -sh $(python -c 'import sys;print(sys.prefix)')"))

	# 磁盘占用
	print("\n[df -h]")
	print(run("df -h | cat"))


if __name__ == "__main__":
	main()


