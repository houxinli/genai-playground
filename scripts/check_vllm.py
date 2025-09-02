#!/usr/bin/env python3
"""
vLLM 状态检查工具
使用 localhost API 检查服务状态
"""

import requests
import json
import sys
import time

def check_vllm_status():
    """检查vLLM服务状态"""
    try:
        # 检查模型列表
        response = requests.get("http://localhost:8000/v1/models", timeout=5)
        
        if response.status_code == 200:
            models = response.json()
            print("✅ vLLM 服务正在运行")
            print(f"📊 端口: 8000")
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
        print("❌ 无法连接到 vLLM 服务 (localhost:8000)")
        print("💡 请检查服务是否已启动")
        return False
    except requests.exceptions.Timeout:
        print("❌ 连接 vLLM 服务超时")
        return False
    except Exception as e:
        print(f"❌ 检查状态时出错: {e}")
        return False

def wait_for_service(max_wait=300):
    """等待服务启动"""
    print(f"⏳ 等待 vLLM 服务启动 (最多 {max_wait} 秒)...")
    
    for i in range(max_wait):
        if check_vllm_status():
            print("🎉 服务已就绪！")
            return True
        
        if i % 10 == 0:
            print(f"⏳ 已等待 {i} 秒...")
        
        time.sleep(1)
    
    print("⏰ 等待超时，服务可能启动失败")
    return False

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "wait":
        wait_for_service()
    else:
        check_vllm_status()

if __name__ == "__main__":
    main()
