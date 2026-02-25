#!/usr/bin/env python3
"""
vLLM 状态检查工具
使用 localhost API 检查服务状态
"""

import requests
import json
import sys
import time
import os

def check_vllm_status(base_url: str | None = None):
    """检查vLLM服务状态"""
    try:
        # 解析 Base URL（参数 > 环境变量 > 默认 localhost）
        base = base_url or os.environ.get("VLLM_BASE_URL") or "http://localhost:8000"
        # 检查模型列表
        response = requests.get(f"{base.rstrip('/')}/v1/models", timeout=5)
        
        if response.status_code == 200:
            models = response.json()
            print("✅ vLLM 服务正在运行")
            print(f"📊 Base: {base}")
            print(f"📦 可用模型:")
            
            for model in models.get('data', []):
                print(f"  - {model['id']}")
                print(f"    最大长度: {model.get('max_model_len', 'N/A')}")
                print(f"    创建时间: {model.get('created', 'N/A')}")
            
            return True
        else:
            print(f"❌ vLLM 服务响应异常: {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到 vLLM 服务 (请检查 VLLM_BASE_URL 或端口)")
        print("💡 请检查服务是否已启动")
        return False
    except requests.exceptions.Timeout:
        print("❌ 连接 vLLM 服务超时")
        return False
    except Exception as e:
        print(f"❌ 检查状态时出错: {e}")
        return False

def wait_for_service(max_wait=300, base_url: str | None = None):
    """等待服务启动"""
    print(f"⏳ 等待 vLLM 服务启动 (最多 {max_wait} 秒)...")
    
    for i in range(max_wait):
        if check_vllm_status(base_url=base_url):
            print("🎉 服务已就绪！")
            return True
        
        if i % 10 == 0:
            print(f"⏳ 已等待 {i} 秒...")
        
        time.sleep(1)
    
    print("⏰ 等待超时，服务可能启动失败")
    return False

def main():
    # 支持：python check_vllm.py [BASE_URL] | python check_vllm.py wait [BASE_URL]
    base_url = None
    if len(sys.argv) >= 2 and sys.argv[1] not in ("wait", "--help", "-h"):
        base_url = sys.argv[1]
    if len(sys.argv) > 1 and sys.argv[1] == "wait":
        # 可选第三个参数作为 base_url
        if len(sys.argv) >= 3:
            base_url = sys.argv[2]
        wait_for_service(base_url=base_url)
    else:
        check_vllm_status(base_url=base_url)

if __name__ == "__main__":
    main()
