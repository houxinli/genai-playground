#!/usr/bin/env python3
"""Test script for Douban API research."""

import requests
import json
import sys
from pathlib import Path

def test_douban_miniprogram_api():
    """Test Douban miniprogram API."""
    print("🔍 Testing Douban Miniprogram API...")
    
    # 豆瓣小程序API配置
    api_host = "https://frodo.douban.com"
    api_key = "0ac44ae016490db2204ce0a042db2916"
    
    headers = {
        'User-Agent': 'MicroMessenger/',
        'Referer': 'https://servicewechat.com/wx2f9b06c1de1ccfca/91/page-frame.html',
        'apiKey': api_key,
        'Accept': 'application/json',
        'Content-Type': 'application/json',
    }
    
    # 测试电影搜索接口
    search_url = f"{api_host}/api/v2/search/movie"
    params = {
        'q': '复仇者联盟',
        'count': 20,
        'start': 0
    }
    
    try:
        print(f"📡 Making request to: {search_url}")
        print(f"📋 Headers: {json.dumps(headers, indent=2, ensure_ascii=False)}")
        print(f"📋 Params: {json.dumps(params, indent=2, ensure_ascii=False)}")
        
        response = requests.get(search_url, headers=headers, params=params, timeout=15)
        
        print(f"📊 Response Status: {response.status_code}")
        print(f"📊 Response Headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Success! Response data:")
            print(json.dumps(data, indent=2, ensure_ascii=False))
            
            # 分析响应数据结构
            if 'subjects' in data:
                movies = data['subjects']
                print(f"\n🎬 Found {len(movies)} movies:")
                for movie in movies[:3]:  # 显示前3部电影
                    title = movie.get('title', 'N/A')
                    rating = movie.get('rating', {})
                    rating_value = rating.get('average', 'N/A') if rating else 'N/A'
                    print(f"   - {title}: {rating_value}")
            
            return True
        else:
            print(f"❌ Failed with status {response.status_code}")
            print(f"Response text: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_douban_web_search():
    """Test Douban web search (alternative approach)."""
    print("\n🔍 Testing Douban Web Search...")
    
    # 尝试豆瓣网页搜索
    search_url = "https://www.douban.com/search"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }
    
    params = {
        'cat': '1002',  # 电影分类
        'q': '复仇者联盟'
    }
    
    try:
        print(f"📡 Making request to: {search_url}")
        
        response = requests.get(search_url, headers=headers, params=params, timeout=15)
        
        print(f"📊 Response Status: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ Success! Got HTML response")
            # 这里可以进一步解析HTML来提取电影信息
            return True
        else:
            print(f"❌ Failed with status {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_third_party_api():
    """Test third-party Douban API services."""
    print("\n🔍 Testing Third-party Douban API...")
    
    # 测试第三方API服务
    api_url = "https://www.doubanapi.com/api/v2/search/movie"
    params = {
        'q': '复仇者联盟',
        'count': 20
    }
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
        'Accept': 'application/json',
    }
    
    try:
        print(f"📡 Making request to: {api_url}")
        
        response = requests.get(api_url, headers=headers, params=params, timeout=15)
        
        print(f"📊 Response Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Success! Response data:")
            print(json.dumps(data, indent=2, ensure_ascii=False))
            return True
        else:
            print(f"❌ Failed with status {response.status_code}")
            print(f"Response text: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def main():
    """Main test function."""
    print("🎬 Douban API Research Tool")
    print("=" * 50)
    
    results = {}
    
    # 测试各种API方案
    results['miniprogram'] = test_douban_miniprogram_api()
    results['web_search'] = test_douban_web_search()
    results['third_party'] = test_third_party_api()
    
    # 总结结果
    print("\n📊 Test Results Summary:")
    print("=" * 50)
    
    for method, success in results.items():
        status = "✅ Success" if success else "❌ Failed"
        print(f"   {method}: {status}")
    
    successful_methods = [method for method, success in results.items() if success]
    
    if successful_methods:
        print(f"\n🎉 Found {len(successful_methods)} working method(s): {successful_methods}")
        print("💡 Recommendation: Use the most reliable method for production")
    else:
        print("\n😞 No working methods found.")
        print("💡 Consider alternative approaches or manual data collection")


if __name__ == "__main__":
    main()
