#!/usr/bin/env python3
"""Fetch Fandango showtimes with multiple rating sources (Douban + IMDb)."""

import json
import sys
from pathlib import Path
from datetime import date, datetime
from typing import List, Dict, Any

SCRIPT_PATH = Path(__file__).resolve()
SUNDAY_MOVIES_ROOT = SCRIPT_PATH.parents[2]
SRC_DIR = SUNDAY_MOVIES_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from collectors.fandango import FandangoShowtimeCollector
from collectors.models import MovieSchedule
from ratings.douban import DoubanFetcher
from ratings.imdb import ImdbFetcher
from ratings.rottentomatoes import RottenTomatoesFetcher
from ratings.aggregator import RatingsAggregator


def fetch_showtimes_with_all_ratings(
    theater_id: str,
    theater_name: str,
    target_date: date,
    max_movies: int = 10
) -> List[Dict[str, Any]]:
    """Fetch showtimes from Fandango and add ratings from multiple sources."""
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
    
    # 初始化评分抓取器
    douban_fetcher = DoubanFetcher(delay=1.5)
    imdb_fetcher = ImdbFetcher()
    rt_fetcher = RottenTomatoesFetcher()
    
    # 创建评分聚合器
    aggregator = RatingsAggregator([douban_fetcher, imdb_fetcher, rt_fetcher])
    
    # 处理每个电影
    results = []
    processed_count = 0
    
    for schedule in schedules:
        if processed_count >= max_movies:
            print(f"📊 Processed {max_movies} movies (limit reached)")
            break
        
        movie_title = schedule.movie_title
        print(f"\n🎭 Processing: {movie_title}")
        
        # 获取多源评分
        try:
            ratings = aggregator.fetch(movie_title, year=2025)
            
            if ratings:
                print(f"   ✅ Found {len(ratings)} rating(s):")
                for rating in ratings:
                    print(f"      📊 {rating.source}: {rating.score:.1f}/{rating.scale} (confidence: {rating.confidence:.2f})")
            else:
                print(f"   ❌ No ratings found")
                ratings = []
                
        except Exception as e:
            print(f"   ❌ Error fetching ratings: {e}")
            ratings = []
        
        # 构建结果
        movie_data = {
            "title": movie_title,
            "showtimes": [],
            "ratings": {},
            "aggregated_score": None,
            "rating_count": len(ratings),
            "local_title": None,
        }
        
        # 处理各个评分源的数据
        for rating in ratings:
            movie_data["ratings"][rating.source] = {
                "score": rating.score,
                "scale": rating.scale,
                "confidence": rating.confidence,
                "summary": rating.summary,
                "url": rating.url,
                "local_title": rating.local_title,
            }
            if rating.source == "douban" and rating.local_title and not movie_data["local_title"]:
                movie_data["local_title"] = rating.local_title
        
        # 计算聚合评分
        if ratings:
            # 简单的加权平均（统一换算成 10 分制）
            total_weight = sum(r.confidence for r in ratings)
            weighted_sum = 0.0
            for r in ratings:
                normalized = r.score
                if r.scale and r.scale != 10:
                    normalized = (r.score / r.scale) * 10
                weighted_sum += normalized * r.confidence
            if total_weight > 0:
                movie_data["aggregated_score"] = weighted_sum / total_weight
                print(f"   🎯 Aggregated score: {movie_data['aggregated_score']:.1f}/10")
        
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
    movies_with_ratings = sum(1 for r in results if r["rating_count"] > 0)
    movies_with_aggregated = sum(1 for r in results if r["aggregated_score"] is not None)
    
    print(f"🎬 Total movies: {total_movies}")
    print(f"📊 Movies with ratings: {movies_with_ratings}")
    print(f"🎯 Movies with aggregated scores: {movies_with_aggregated}")
    print(f"📈 Rating coverage: {movies_with_ratings/total_movies*100:.1f}%")
    
    # 统计各评分源的成功率
    douban_count = sum(1 for r in results if "douban" in r["ratings"])
    imdb_count = sum(1 for r in results if "imdb" in r["ratings"])
    rt_count = sum(1 for r in results if "rottentomatoes" in r["ratings"])
    
    print(f"\n📊 Rating Source Success:")
    print(f"   🟢 Douban: {douban_count}/{total_movies} ({douban_count/total_movies*100:.1f}%)")
    print(f"   🔵 IMDb: {imdb_count}/{total_movies} ({imdb_count/total_movies*100:.1f}%)")
    print(f"   🍅 Rotten Tomatoes: {rt_count}/{total_movies} ({rt_count/total_movies*100:.1f}%)")
    
    print(f"\n🎯 Top Rated Movies (by aggregated score):")
    # 按聚合评分排序
    rated_movies = [r for r in results if r["aggregated_score"] is not None]
    rated_movies.sort(key=lambda x: x["aggregated_score"], reverse=True)
    
    for i, movie in enumerate(rated_movies[:5]):
        title = movie["title"]
        if movie.get("local_title") and movie["local_title"] != movie["title"]:
            title = f"{movie['title']} / {movie['local_title']}"
        score = movie["aggregated_score"]
        rating_count = movie["rating_count"]
        showtime_count = len(movie["showtimes"])
        
        # 显示各评分源的评分
        rating_info = []
        for source, rating_data in movie["ratings"].items():
            scale = rating_data.get("scale", 10)
            rating_info.append(f"{source}: {rating_data['score']:.1f}/{scale}")
        
        rating_str = " | ".join(rating_info)
        
        print(f"   {i+1}. {title}: {score:.1f}/10 ({rating_str}, {showtime_count} showtimes)")


def print_markdown_table(results: List[Dict[str, Any]]) -> None:
    """Output Markdown table sorted by showtime count."""
    print("\n📝 Markdown 排片表（按场次数量排序）")
    print("| English Title | 中文标题 | Aggregated Score | Showtimes |")
    print("| --- | --- | --- | --- |")
    
    sorted_results = sorted(results, key=lambda r: len(r["showtimes"]), reverse=True)
    
    for movie in sorted_results:
        english = movie["title"]
        chinese = movie.get("local_title") or "—"
        score = movie["aggregated_score"]
        score_str = f"{score:.1f}/10" if score is not None else "—"
        
        showtimes = []
        for st in movie["showtimes"]:
            try:
                time_obj = datetime.fromisoformat(st["start_time"])
                showtimes.append(time_obj.strftime("%H:%M"))
            except Exception:
                continue
        showtimes_str = f"{len(showtimes)} 场: {', '.join(showtimes)}" if showtimes else "—"
        
        print(f"| {english} | {chinese} | {score_str} | {showtimes_str} |")


def save_results(results: List[Dict[str, Any]], output_file: Path) -> None:
    """Save results to JSON file."""
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    output_data = {
        "timestamp": date.today().isoformat(),
        "total_movies": len(results),
        "movies_with_ratings": sum(1 for r in results if r["rating_count"] > 0),
        "movies_with_aggregated_scores": sum(1 for r in results if r["aggregated_score"] is not None),
        "rating_sources": {
            "douban": sum(1 for r in results if "douban" in r["ratings"]),
            "imdb": sum(1 for r in results if "imdb" in r["ratings"]),
            "rottentomatoes": sum(1 for r in results if "rottentomatoes" in r["ratings"]),
        },
        "movies": results
    }
    
    with output_file.open("w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Results saved to: {output_file}")


def main():
    """Main function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Fetch Fandango showtimes with multiple rating sources")
    parser.add_argument("--theater-id", required=True, help="Fandango theater ID")
    parser.add_argument("--theater-name", required=True, help="Theater name")
    parser.add_argument("--date", type=lambda s: date.fromisoformat(s), default=date.today(), help="Date (YYYY-MM-DD)")
    parser.add_argument("--max-movies", type=int, default=10, help="Maximum number of movies to process")
    parser.add_argument("--output", type=Path, help="Output JSON file path")
    
    args = parser.parse_args()
    
    print("🎬 Fandango Showtimes with Multi-Source Ratings")
    print("=" * 60)
    print(f"🎭 Theater: {args.theater_name} ({args.theater_id})")
    print(f"📅 Date: {args.date}")
    print(f"🎯 Max movies: {args.max_movies}")
    print(f"📊 Rating sources: Douban + IMDb + Rotten Tomatoes")
    
    # 获取场次和评分数据
    results = fetch_showtimes_with_all_ratings(
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
    print_markdown_table(results)
    
    # 保存结果
    if args.output:
        save_results(results, args.output)
    else:
        # 默认保存路径
        default_output = SUNDAY_MOVIES_ROOT / "data" / f"showtimes_multi_ratings_{args.date.isoformat()}.json"
        save_results(results, default_output)


if __name__ == "__main__":
    main()
