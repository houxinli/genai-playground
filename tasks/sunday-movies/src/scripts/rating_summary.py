#!/usr/bin/env python3
"""Generate a rating summary report from the multi-ratings data."""

import json
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
SUNDAY_MOVIES_ROOT = SCRIPT_PATH.parents[2]
DATA_DIR = SUNDAY_MOVIES_ROOT / "data"


def load_rating_data(date_str: str) -> dict:
    """Load rating data from JSON file."""
    file_path = DATA_DIR / f"showtimes_multi_ratings_{date_str}.json"
    
    if not file_path.exists():
        print(f"❌ Data file not found: {file_path}")
        return {}
    
    with file_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def generate_summary(data: dict) -> None:
    """Generate a comprehensive rating summary."""
    if not data:
        return
    
    movies = data.get("movies", [])
    total_movies = len(movies)
    movies_with_ratings = data.get("movies_with_ratings", 0)
    coverage = (movies_with_ratings / total_movies * 100) if total_movies > 0 else 0
    
    print("🎬 AMC Mercado 20 - 电影评分总结报告")
    print("=" * 60)
    print(f"📅 日期: {data.get('timestamp', 'N/A')}")
    print(f"🎭 影院: AMC Mercado 20")
    print(f"📊 总电影数: {total_movies}")
    print(f"✅ 有评分的电影: {movies_with_ratings}")
    print(f"📈 评分覆盖率: {coverage:.1f}%")
    
    # 评分源统计
    rating_sources = data.get("rating_sources", {})
    douban_count = rating_sources.get("douban", 0)
    imdb_count = rating_sources.get("imdb", 0)
    
    print(f"\n📊 评分源成功率:")
    print(f"   🟢 豆瓣: {douban_count}/{total_movies} ({douban_count/total_movies*100:.1f}%)")
    print(f"   🔵 IMDb: {imdb_count}/{total_movies} ({imdb_count/total_movies*100:.1f}%)")
    
    # 按评分排序的电影列表
    rated_movies = [m for m in movies if m.get("aggregated_score")]
    rated_movies.sort(key=lambda x: x["aggregated_score"], reverse=True)
    
    print(f"\n🏆 评分排行榜 (Top 15):")
    print("-" * 60)
    
    for i, movie in enumerate(rated_movies[:15]):
        title = movie["title"]
        score = movie["aggregated_score"]
        rating_count = movie.get("rating_count", 0)
        showtime_count = len(movie.get("showtimes", []))
        
        # 显示各评分源的评分
        rating_info = []
        ratings = movie.get("ratings", {})
        
        if "douban" in ratings:
            douban_score = ratings["douban"]["score"]
            rating_info.append(f"豆瓣: {douban_score:.1f}")
        
        if "imdb" in ratings:
            imdb_score = ratings["imdb"]["score"]
            rating_info.append(f"IMDb: {imdb_score:.1f}")
        
        rating_str = " | ".join(rating_info)
        
        print(f"{i+1:2d}. {title}")
        print(f"    📊 综合评分: {score:.1f}/10 ({rating_str})")
        print(f"    🎬 场次: {showtime_count} | 评分源: {rating_count}")
        print()
    
    # 评分分布统计
    print(f"\n📊 评分分布统计:")
    print("-" * 30)
    
    excellent = sum(1 for m in rated_movies if m["aggregated_score"] >= 8.0)
    good = sum(1 for m in rated_movies if 7.0 <= m["aggregated_score"] < 8.0)
    average = sum(1 for m in rated_movies if 6.0 <= m["aggregated_score"] < 7.0)
    poor = sum(1 for m in rated_movies if m["aggregated_score"] < 6.0)
    
    print(f"   🌟 优秀 (8.0+): {excellent} 部 ({excellent/len(rated_movies)*100:.1f}%)")
    print(f"   👍 良好 (7.0-7.9): {good} 部 ({good/len(rated_movies)*100:.1f}%)")
    print(f"   👌 一般 (6.0-6.9): {average} 部 ({average/len(rated_movies)*100:.1f}%)")
    print(f"   👎 较差 (<6.0): {poor} 部 ({poor/len(rated_movies)*100:.1f}%)")
    
    # 没有评分的电影
    no_rating_movies = [m for m in movies if not m.get("aggregated_score")]
    if no_rating_movies:
        print(f"\n❓ 暂无评分的电影 ({len(no_rating_movies)} 部):")
        print("-" * 30)
        for movie in no_rating_movies:
            print(f"   • {movie['title']}")
    
    # 推荐电影
    print(f"\n🎯 推荐观看 (评分 7.0+ 的电影):")
    print("-" * 40)
    recommended = [m for m in rated_movies if m["aggregated_score"] >= 7.0]
    
    for movie in recommended:
        title = movie["title"]
        score = movie["aggregated_score"]
        showtime_count = len(movie.get("showtimes", []))
        
        # 获取最早的场次时间
        showtimes = movie.get("showtimes", [])
        if showtimes:
            earliest_time = min(s["start_time"] for s in showtimes)
            print(f"   🎬 {title} ({score:.1f}/10) - 最早场次: {earliest_time}")
        else:
            print(f"   🎬 {title} ({score:.1f}/10)")


def main():
    """Main function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate rating summary report")
    parser.add_argument("--date", default="2025-10-19", help="Date in YYYY-MM-DD format")
    
    args = parser.parse_args()
    
    # 加载数据
    data = load_rating_data(args.date)
    
    if not data:
        print("❌ No data available")
        return
    
    # 生成总结报告
    generate_summary(data)


if __name__ == "__main__":
    main()
