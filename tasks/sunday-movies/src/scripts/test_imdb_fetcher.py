#!/usr/bin/env python3
"""Test script for IMDb rating fetcher."""

import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
SUNDAY_MOVIES_ROOT = SCRIPT_PATH.parents[2]
SRC_DIR = SUNDAY_MOVIES_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ratings.imdb import ImdbFetcher


def test_imdb_fetcher():
    """Test the IMDb rating fetcher with sample movies."""
    print("🎬 Testing IMDb Rating Fetcher")
    print("=" * 50)
    
    fetcher = ImdbFetcher()
    
    # 测试电影列表
    test_movies = [
        ("Black Phone 2", 2025),
        ("Tron: Ares", 2025),
        ("Demon Slayer: Kimetsu no Yaiba Infinity Castle", 2025),
        ("After the Hunt", 2025),
        ("Spirited Away", 2001),  # 经典电影，应该有评分
    ]
    
    results = []
    
    for title, year in test_movies:
        print(f"\n🎭 Testing: {title} ({year})")
        print("-" * 40)
        
        try:
            result = fetcher.fetch(title, year=year)
            
            if result:
                print(f"✅ Success!")
                print(f"   📊 Rating: {result.score}/{result.scale}")
                print(f"   🔗 URL: {result.url}")
                print(f"   📝 Summary: {result.summary}")
                print(f"   🎯 Confidence: {result.confidence:.2f}")
                
                results.append({
                    'title': title,
                    'year': year,
                    'success': True,
                    'rating': result.score,
                    'confidence': result.confidence,
                    'summary': result.summary
                })
            else:
                print("❌ No rating found")
                results.append({
                    'title': title,
                    'year': year,
                    'success': False,
                    'rating': None,
                    'confidence': 0,
                    'summary': None
                })
                
        except Exception as e:
            print(f"❌ Error: {e}")
            results.append({
                'title': title,
                'year': year,
                'success': False,
                'rating': None,
                'confidence': 0,
                'summary': None,
                'error': str(e)
            })
    
    # 总结结果
    print("\n📊 Test Results Summary:")
    print("=" * 50)
    
    successful_tests = sum(1 for r in results if r['success'])
    total_tests = len(results)
    success_rate = successful_tests / total_tests * 100
    
    print(f"🎯 Success Rate: {successful_tests}/{total_tests} ({success_rate:.1f}%)")
    print()
    
    for result in results:
        status = "✅" if result['success'] else "❌"
        rating_info = f"({result['rating']:.1f})" if result['rating'] else "(N/A)"
        print(f"   {status} {result['title']} {rating_info}")
    
    if successful_tests > 0:
        avg_confidence = sum(r['confidence'] for r in results if r['success']) / successful_tests
        print(f"\n📈 Average Confidence: {avg_confidence:.2f}")
        
        # 显示一些成功的示例
        successful_results = [r for r in results if r['success']]
        if successful_results:
            print(f"\n🎉 Sample Success Results:")
            for result in successful_results[:2]:
                print(f"   📽️  {result['title']}: {result['rating']:.1f}/10")
                print(f"      {result['summary']}")
    
    return results


def main():
    """Main test function."""
    print("🎬 IMDb Rating Fetcher Test Suite")
    print("=" * 60)
    
    # 基础功能测试
    basic_results = test_imdb_fetcher()
    
    # 评估结果
    success_rate = sum(1 for r in basic_results if r['success']) / len(basic_results)
    
    print(f"\n💡 Assessment:")
    if success_rate >= 0.8:
        print("✅ IMDb fetcher is highly effective")
        print("💡 Ready for integration with rating aggregation")
    elif success_rate >= 0.5:
        print("⚠️  IMDb fetcher is moderately effective")
        print("💡 Consider improvements before production use")
    else:
        print("❌ IMDb fetcher needs significant improvements")
        print("💡 Review implementation and error handling")
    
    print(f"\n🚀 Next Steps:")
    print("1. Integrate IMDb with Douban ratings")
    print("2. Create multi-source rating aggregation")
    print("3. Test with Fandango showtime data")
    print("4. Optimize performance and error handling")


if __name__ == "__main__":
    main()
