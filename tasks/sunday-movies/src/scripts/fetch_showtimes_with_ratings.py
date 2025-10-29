#!/usr/bin/env python3
"""Fetch Fandango showtimes with Douban ratings."""

import json
import sys
from pathlib import Path
from datetime import date
from typing import List, Dict, Any

SCRIPT_PATH = Path(__file__).resolve()
SUNDAY_MOVIES_ROOT = SCRIPT_PATH.parents[2]
SRC_DIR = SUNDAY_MOVIES_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from collectors.fandango import FandangoShowtimeCollector
from collectors.models import MovieSchedule
from ratings.douban import DoubanFetcher
from ratings.aggregator import RatingsAggregator


def fetch_showtimes_with_ratings(
    theater_id: str,
    theater_name: str,
    target_date: date,
    max_movies: int = 10
) -> List[Dict[str, Any]]:
    """Fetch showtimes from Fandango and add Douban ratings."""
    print(f"🎬 Fetching showtimes for {theater_name} ({theater_id}) on {target_date}")
    
    # 获取Fandango场次数据
    collector = FandangoShowtimeCollector()
    schedules = collector.fetch_showtimes(
        theater_id=theater_id,
        theater_name=theater_name,
        date=target_date,
    )
    
    if not schedules:
        print("❌ No showtimes found")
        return []
    
    print(f"✅ Found {len(schedules)} movies")
    
    # 初始化豆瓣评分抓取器
    douban_fetcher = DoubanFetcher(delay=1.5)  # 增加延迟避免被限制
    
    # 处理每个电影
    results = []
    processed_count = 0
    
    for schedule in schedules:
        if processed_count >= max_movies:
            print(f"📊 Processed {max_movies} movies (limit reached)")
            break
        
        movie_title = schedule.movie_title
        print(f"\n🎭 Processing: {movie_title}")
        
        # 获取豆瓣评分
        try:
            rating_result = douban_fetcher.fetch(movie_title, year=2025)
            
            if rating_result:
                print(f"   ✅ Douban: {rating_result.score:.1f}/10 (confidence: {rating_result.confidence:.2f})")
            else:
                print(f"   ❌ No Douban rating found")
                rating_result = None
                
        except Exception as e:
            print(f"   ❌ Error fetching rating: {e}")
            rating_result = None
        
        # 构建结果
        movie_data = {
            "title": movie_title,
            "showtimes": [],
            "rating": {
                "douban": {
                    "score": rating_result.score if rating_result else None,
                    "scale": rating_result.scale if rating_result else None,
                    "confidence": rating_result.confidence if rating_result else 0,
                    "summary": rating_result.summary if rating_result else None,
                    "url": rating_result.url if rating_result else None,
                }
            }
        }
        
        # 添加场次信息
        for showtime in schedule.showtimes:
            showtime_data = {
                "start_time": showtime.start_time.isoformat(),
                "format_tags": showtime.format_tags,
                "booking_url": showtime.booking_url,
                "auditorium": showtime.auditorium,
            }
            movie_data["showtimes"].append(showtime_data)
        
        results.append(movie_data)
        processed_count += 1
    
    return results


def print_summary(results: List[Dict[str, Any]]) -> None:
    """Print a summary of the results."""
    print(f"\n📊 Summary:")
    print("=" * 50)
    
    total_movies = len(results)
    movies_with_ratings = sum(1 for r in results if r["rating"]["douban"]["score"] is not None)
    
    print(f"🎬 Total movies: {total_movies}")
    print(f"📊 Movies with ratings: {movies_with_ratings}")
    print(f"📈 Rating coverage: {movies_with_ratings/total_movies*100:.1f}%")
    
    print(f"\n🎯 Top Rated Movies:")
    # 按评分排序
    rated_movies = [r for r in results if r["rating"]["douban"]["score"] is not None]
    rated_movies.sort(key=lambda x: x["rating"]["douban"]["score"], reverse=True)
    
    for i, movie in enumerate(rated_movies[:5]):
        title = movie["title"]
        score = movie["rating"]["douban"]["score"]
        confidence = movie["rating"]["douban"]["confidence"]
        showtime_count = len(movie["showtimes"])
        print(f"   {i+1}. {title}: {score:.1f}/10 (confidence: {confidence:.2f}, {showtime_count} showtimes)")


def save_results(results: List[Dict[str, Any]], output_file: Path) -> None:
    """Save results to JSON file."""
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    output_data = {
        "timestamp": date.today().isoformat(),
        "total_movies": len(results),
        "movies_with_ratings": sum(1 for r in results if r["rating"]["douban"]["score"] is not None),
        "movies": results
    }
    
    with output_file.open("w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Results saved to: {output_file}")


def main():
    """Main function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Fetch Fandango showtimes with Douban ratings")
    parser.add_argument("--theater-id", required=True, help="Fandango theater ID")
    parser.add_argument("--theater-name", required=True, help="Theater name")
    parser.add_argument("--date", type=lambda s: date.fromisoformat(s), default=date.today(), help="Date (YYYY-MM-DD)")
    parser.add_argument("--max-movies", type=int, default=10, help="Maximum number of movies to process")
    parser.add_argument("--output", type=Path, help="Output JSON file path")
    
    args = parser.parse_args()
    
    print("🎬 Fandango Showtimes with Douban Ratings")
    print("=" * 50)
    print(f"🎭 Theater: {args.theater_name} ({args.theater_id})")
    print(f"📅 Date: {args.date}")
    print(f"🎯 Max movies: {args.max_movies}")
    
    # 获取场次和评分数据
    results = fetch_showtimes_with_ratings(
        theater_id=args.theater_id,
        theater_name=args.theater_name,
        target_date=args.date,
        max_movies=args.max_movies
    )
    
    if not results:
        print("❌ No results to display")
        return
    
    # 显示摘要
    print_summary(results)
    
    # 保存结果
    if args.output:
        save_results(results, args.output)
    else:
        # 默认保存路径
        default_output = SUNDAY_MOVIES_ROOT / "data" / f"showtimes_with_ratings_{args.date.isoformat()}.json"
        save_results(results, default_output)


if __name__ == "__main__":
    main()
