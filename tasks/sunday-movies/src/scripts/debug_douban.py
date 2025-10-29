#!/usr/bin/env python3
"""Debug script for Douban rating fetcher."""

import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
SUNDAY_MOVIES_ROOT = SCRIPT_PATH.parents[2]
SRC_DIR = SUNDAY_MOVIES_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ratings.douban import DoubanFetcher


def debug_search_process():
    """Debug the search process step by step."""
    print("🔍 Debugging Douban Search Process")
    print("=" * 50)
    
    fetcher = DoubanFetcher(delay=1.0)
    test_title = "Black Phone 2"
    
    print(f"🎭 Testing with: {test_title}")
    print("-" * 30)
    
    # 步骤1: 搜索电影
    print("📡 Step 1: Searching movies...")
    search_results = fetcher._search_movies(test_title)
    print(f"   Found {len(search_results)} results")
    
    for i, movie in enumerate(search_results):
        print(f"   {i+1}. {movie['title']} - Rating: {movie['rating']}")
        print(f"      URL: {movie['url']}")
        print(f"      Info: {movie['info'][:100]}...")
    
    if not search_results:
        print("   ❌ No search results found")
        return
    
    # 步骤2: 选择最佳匹配
    print(f"\n🎯 Step 2: Selecting best match...")
    best_match = fetcher._select_best_match(search_results, test_title, 2025)
    if best_match:
        print(f"   ✅ Best match: {best_match['title']}")
        print(f"   📊 Rating: {best_match['rating']}")
        print(f"   🔗 URL: {best_match['url']}")
    else:
        print("   ❌ No best match found")
        return
    
    # 步骤3: 获取详细信息
    print(f"\n📖 Step 3: Getting movie details...")
    details = fetcher._get_movie_details(best_match['url'])
    if details:
        print(f'   ✅ Details found: {details}')
    else:
        print("   ❌ No details found")
        return
    
    # 步骤4: 构建评分结果
    print(f"\n🏗️ Step 4: Building rating result...")
    result = fetcher._build_rating_result(details, best_match)
    if result:
        print(f"   ✅ Rating result:")
        print(f"      Score: {result.score}/{result.scale}")
        print(f"      Confidence: {result.confidence}")
        print(f"      Summary: {result.summary}")
    else:
        print("   ❌ Failed to build rating result")


def debug_with_different_titles():
    """Test with different movie titles to find working examples."""
    print("\n🎬 Testing Different Movie Titles")
    print("=" * 50)
    
    fetcher = DoubanFetcher(delay=1.0)
    
    # 测试一些已知在豆瓣上存在的电影
    test_titles = [
        "复仇者联盟",
        "泰坦尼克号", 
        "肖申克的救赎",
        "阿甘正传",
        "盗梦空间",
        "星际穿越",
        "黑豹",
        "蜘蛛侠",
    ]
    
    for title in test_titles:
        print(f"\n🎭 Testing: {title}")
        print("-" * 20)
        
        try:
            result = fetcher.fetch(title)
            if result:
                print(f"   ✅ Success: {result.score:.1f}/10")
                print(f"   📝 Summary: {result.summary}")
            else:
                print("   ❌ No result")
        except Exception as e:
            print(f"   ❌ Error: {e}")


def debug_html_parsing():
    """Debug HTML parsing by examining actual responses."""
    print("\n🔍 Debugging HTML Parsing")
    print("=" * 50)
    
    import requests
    from bs4 import BeautifulSoup
    
    # 直接测试豆瓣搜索页面
    search_url = "https://www.douban.com/search"
    params = {'cat': '1002', 'q': '复仇者联盟'}
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }
    
    try:
        print(f"📡 Making request to: {search_url}")
        response = requests.get(search_url, params=params, headers=headers, timeout=15)
        print(f"📊 Status: {response.status_code}")
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 查找搜索结果容器
            result_items = soup.find_all('div', class_='result')
            print(f"🔍 Found {len(result_items)} result items")
            
            if result_items:
                # 检查第一个结果的HTML结构
                first_result = result_items[0]
                print(f"\n📋 First result HTML structure:")
                print(f"   Classes: {first_result.get('class', [])}")
                
                # 查找标题元素
                title_div = first_result.find('div', class_='title')
                if title_div:
                    print(f"   Title div found: {title_div.get('class', [])}")
                    link = title_div.find('a')
                    if link:
                        print(f"   Title link: {link.get_text(strip=True)}")
                        print(f"   Title URL: {link.get('href', '')}")
                    else:
                        print("   ❌ No title link found")
                else:
                    print("   ❌ No title div found")
                
                # 查找评分元素
                rating_span = first_result.find('span', class_='rating_nums')
                if rating_span:
                    print(f"   Rating found: {rating_span.get_text(strip=True)}")
                else:
                    print("   ❌ No rating found")
                    # 尝试其他可能的评分元素
                    all_spans = first_result.find_all('span')
                    print(f"   All spans: {[span.get('class', []) for span in all_spans]}")
            
        else:
            print(f"❌ Request failed with status {response.status_code}")
            
    except Exception as e:
        print(f"❌ Error: {e}")


def main():
    """Main debug function."""
    print("🐛 Douban Rating Fetcher Debug Tool")
    print("=" * 60)
    
    # 调试搜索过程
    debug_search_process()
    
    # 测试不同的电影标题
    debug_with_different_titles()
    
    # 调试HTML解析
    debug_html_parsing()
    
    print(f"\n💡 Debug Summary:")
    print("1. Check if search results are being found")
    print("2. Verify HTML parsing is working correctly")
    print("3. Test with known working movie titles")
    print("4. Examine the actual HTML structure of search results")


if __name__ == "__main__":
    main()
