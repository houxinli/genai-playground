#!/usr/bin/env python3
"""Test script for Douban web scraping approach."""

import requests
from bs4 import BeautifulSoup
import json
import sys
import time
from pathlib import Path

def search_douban_movies(movie_title: str) -> list:
    """Search for movies on Douban using web scraping."""
    print(f"🔍 Searching for '{movie_title}' on Douban...")
    
    search_url = "https://www.douban.com/search"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    
    params = {
        'cat': '1002',  # 电影分类
        'q': movie_title
    }
    
    try:
        response = requests.get(search_url, headers=headers, params=params, timeout=15)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 查找电影搜索结果
            movies = []
            result_items = soup.find_all('div', class_='result')
            
            for item in result_items[:5]:  # 只取前5个结果
                try:
                    # 提取电影标题
                    title_link = item.find('div', class_='title').find('a')
                    if not title_link:
                        continue
                        
                    title = title_link.get_text(strip=True)
                    movie_url = title_link.get('href', '')
                    
                    # 提取评分
                    rating_span = item.find('span', class_='rating_nums')
                    rating = rating_span.get_text(strip=True) if rating_span else 'N/A'
                    
                    # 提取其他信息
                    info_div = item.find('div', class_='info')
                    info_text = info_div.get_text(strip=True) if info_div else ''
                    
                    movie_data = {
                        'title': title,
                        'rating': rating,
                        'url': movie_url,
                        'info': info_text
                    }
                    movies.append(movie_data)
                    
                except Exception as e:
                    print(f"   ⚠️  Error parsing result item: {e}")
                    continue
            
            print(f"✅ Found {len(movies)} movies")
            for movie in movies:
                print(f"   - {movie['title']}: {movie['rating']}")
            
            return movies
            
        else:
            print(f"❌ Failed with status {response.status_code}")
            return []
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return []


def get_movie_details(movie_url: str) -> dict:
    """Get detailed movie information from Douban movie page."""
    print(f"📖 Getting details from: {movie_url}")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }
    
    try:
        response = requests.get(movie_url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            details = {}
            
            # 提取评分
            rating_strong = soup.find('strong', class_='ll rating_num')
            if rating_strong:
                details['rating'] = rating_strong.get_text(strip=True)
            
            # 提取评价人数
            rating_span = soup.find('span', property='v:votes')
            if rating_span:
                details['votes'] = rating_span.get_text(strip=True)
            
            # 提取导演
            director_span = soup.find('span', property='v:director')
            if director_span:
                details['director'] = director_span.get_text(strip=True)
            
            # 提取演员
            actors = soup.find_all('span', property='v:starring')
            if actors:
                details['actors'] = [actor.get_text(strip=True) for actor in actors]
            
            # 提取类型
            genres = soup.find_all('span', property='v:genre')
            if genres:
                details['genres'] = [genre.get_text(strip=True) for genre in genres]
            
            # 提取年份
            year_span = soup.find('span', property='v:initialReleaseDate')
            if year_span:
                details['year'] = year_span.get_text(strip=True)
            
            print(f"   📊 Rating: {details.get('rating', 'N/A')}")
            print(f"   👥 Votes: {details.get('votes', 'N/A')}")
            print(f"   🎬 Director: {details.get('director', 'N/A')}")
            
            return details
            
        else:
            print(f"❌ Failed to get details with status {response.status_code}")
            return {}
            
    except Exception as e:
        print(f"❌ Error getting details: {e}")
        return {}


def test_with_sample_movies():
    """Test with sample movies from our Fandango data."""
    print("🎬 Testing Douban Scraping with Sample Movies")
    print("=" * 50)
    
    # 从Fandango数据中提取一些电影名称进行测试
    test_movies = [
        "Black Phone 2",
        "Tron: Ares",
        "Demon Slayer: Kimetsu no Yaiba Infinity Castle",
        "Spirited Away - Studio Ghibli Fest 2025",
        "After the Hunt"
    ]
    
    results = {}
    
    for movie_title in test_movies:
        print(f"\n🎭 Testing: {movie_title}")
        print("-" * 30)
        
        movies = search_douban_movies(movie_title)
        
        if movies:
            # 获取第一个结果的详细信息
            best_match = movies[0]
            details = get_movie_details(best_match['url'])
            
            results[movie_title] = {
                'search_results': len(movies),
                'best_match': best_match,
                'details': details
            }
            
            # 添加延迟避免被限制
            time.sleep(2)
        else:
            results[movie_title] = {
                'search_results': 0,
                'best_match': None,
                'details': None
            }
    
    # 总结结果
    print("\n📊 Test Results Summary:")
    print("=" * 50)
    
    successful_searches = 0
    for movie, result in results.items():
        status = "✅" if result['search_results'] > 0 else "❌"
        print(f"   {status} {movie}: {result['search_results']} results")
        if result['search_results'] > 0:
            successful_searches += 1
    
    print(f"\n🎯 Success Rate: {successful_searches}/{len(test_movies)} ({successful_searches/len(test_movies)*100:.1f}%)")
    
    return results


def main():
    """Main test function."""
    print("🎬 Douban Web Scraping Test")
    print("=" * 50)
    
    # 测试样本电影
    results = test_with_sample_movies()
    
    # 评估可行性
    success_rate = sum(1 for r in results.values() if r['search_results'] > 0) / len(results)
    
    print(f"\n💡 Assessment:")
    if success_rate >= 0.8:
        print("✅ Web scraping approach is highly feasible")
        print("💡 Recommendation: Implement DoubanFetcher using web scraping")
    elif success_rate >= 0.5:
        print("⚠️  Web scraping approach is moderately feasible")
        print("💡 Recommendation: Implement with fallback options")
    else:
        print("❌ Web scraping approach has limited feasibility")
        print("💡 Recommendation: Consider alternative approaches")


if __name__ == "__main__":
    main()
