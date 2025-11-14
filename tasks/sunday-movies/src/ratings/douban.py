"""Douban rating fetcher using web scraping."""

from __future__ import annotations

import re
import time
from typing import Optional
from urllib.parse import unquote

import requests
from bs4 import BeautifulSoup

from .base import RatingFetcher, RatingResult
from .utils import normalize_title, title_similarity


class DoubanFetcher(RatingFetcher):
    source = "douban"

    SEARCH_URL = "https://www.douban.com/search"
    DEFAULT_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        # requests 没有原生 br 解码能力，因此强制服务端返回 gzip/deflate，避免解析到压缩内容
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    def __init__(self, *, timeout: int = 15, delay: float = 1.0) -> None:
        super().__init__(timeout=timeout)
        self.session = requests.Session()
        self.session.headers.update(self.DEFAULT_HEADERS)
        self.delay = delay

    def fetch(self, title: str, *, year: Optional[int] = None) -> Optional[RatingResult]:
        """Fetch movie rating from Douban using web scraping."""
        try:
            # 搜索电影
            search_results = self._search_movies(title)
            if not search_results:
                return None
            
            # 选择最佳匹配
            best_match = self._select_best_match(search_results, title, year)
            if not best_match:
                return None
            
            # 获取详细信息
            details = self._get_movie_details(best_match['url'])
            
            # 构建评分结果
            return self._build_rating_result(details, best_match)
            
        except Exception as e:
            print(f"Error fetching Douban rating for '{title}': {e}")
            return None

    def _search_movies(self, title: str) -> list:
        """Search for movies on Douban."""
        params = {
            'cat': '1002',  # 电影分类
            'q': title
        }
        
        try:
            response = self.session.get(self.SEARCH_URL, params=params, timeout=self.timeout)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            movies = []
            
            result_items = soup.find_all('div', class_='result')
            
            for item in result_items[:5]:  # 只取前5个结果
                try:
                    # 提取电影标题
                    title_link = item.find('div', class_='title')
                    if not title_link:
                        continue
                    
                    link = title_link.find('a')
                    if not link:
                        continue
                    
                    movie_title = link.get_text(strip=True)
                    movie_url = link.get('href', '')
                    
                    # 提取评分
                    rating_span = item.find('span', class_='rating_nums')
                    rating = rating_span.get_text(strip=True) if rating_span else None
                    
                    # 提取其他信息
                    info_div = item.find('div', class_='info')
                    info_text = info_div.get_text(strip=True) if info_div else ''
                    
                    movie_data = {
                        'title': movie_title,
                        'rating': rating,
                        'url': movie_url,
                        'info': info_text
                    }
                    movies.append(movie_data)
                    
                except Exception as e:
                    continue
            
            # 添加延迟避免被限制
            if self.delay > 0:
                time.sleep(self.delay)
            
            return movies
            
        except Exception as e:
            print(f"Error searching movies: {e}")
            return []

    def _select_best_match(self, movies: list, original_title: str, year: Optional[int]) -> Optional[dict]:
        """Select the best matching movie from search results."""
        if not movies:
            return None
        
        # 如果只有一个结果，直接返回
        if len(movies) == 1:
            return movies[0]
        
        # 计算相似度并选择最佳匹配
        best_match = None
        best_score = 0.0
        
        normalized_original = normalize_title(original_title)
        
        for movie in movies:
            # 计算标题相似度
            similarity = title_similarity(normalized_original, normalize_title(movie['title']))
            
            # 年份匹配加分
            if year and self._extract_year_from_info(movie['info']) == year:
                similarity += 0.2
            
            if similarity > best_score and similarity > 0.3:  # 最低相似度阈值
                best_score = similarity
                best_match = movie
        
        return best_match

    def _get_movie_details(self, movie_url: str) -> Optional[dict]:
        """Get detailed movie information from Douban movie page."""
        try:
            # 处理重定向URL - 直接从URL中提取subject ID
            if 'douban.com/link2/' in movie_url:
                # 从URL中提取真实的豆瓣电影ID
                subject_id = self._extract_subject_id_from_url(movie_url)
                if subject_id:
                    movie_url = f"https://movie.douban.com/subject/{subject_id}/"
            
            response = self.session.get(movie_url, timeout=self.timeout)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            details = {}
            
            # 中文片名
            title_elem = soup.find('span', property='v:itemreviewed')
            if title_elem:
                details['title'] = title_elem.get_text(strip=True)
            
            # 提取评分 - 尝试多种选择器
            rating = None
            rating_selectors = [
                'strong.ll.rating_num',
                'span[property="v:average"]',
                '.rating_num',
                '.ll.rating_num'
            ]
            
            for selector in rating_selectors:
                rating_elem = soup.select_one(selector)
                if rating_elem:
                    rating_text = rating_elem.get_text(strip=True)
                    try:
                        rating = float(rating_text)
                        break
                    except ValueError:
                        continue
            
            if rating:
                details['rating'] = rating
            
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
            
            # 如果从详情页没有获取到评分，尝试从搜索结果中获取
            if not rating:
                # 这里可以返回一个基础的结果，包含搜索时获得的评分
                return None
            
            return details if details else None
            
        except Exception as e:
            print(f"Error getting movie details: {e}")
            return None

    def _extract_subject_id_from_url(self, link_url: str) -> Optional[str]:
        """Extract subject ID from Douban redirect URL."""
        try:
            # 从URL中提取subject ID
            # 例如: https://www.douban.com/link2/?url=https%3A%2F%2Fmovie.douban.com%2Fsubject%2F36621696%2F
            import re
            match = re.search(r'/subject/(\d+)/', link_url)
            if match:
                return match.group(1)
            return None
        except:
            return None

    def _extract_real_douban_url(self, link_url: str) -> Optional[str]:
        """Extract real Douban URL from redirect link."""
        try:
            # 发送HEAD请求获取重定向后的真实URL
            response = self.session.head(link_url, timeout=self.timeout, allow_redirects=True)
            return response.url if response.status_code == 200 else None
        except:
            return None

    def _extract_year_from_info(self, info_text: str) -> Optional[int]:
        """Extract year from movie info text."""
        year_pattern = r'(\d{4})'
        matches = re.findall(year_pattern, info_text)
        if matches:
            try:
                return int(matches[-1])  # 取最后一个年份
            except ValueError:
                pass
        return None

    def _build_rating_result(self, details: dict, movie_info: dict) -> RatingResult:
        """Build RatingResult from movie details."""
        # 优先使用详情页的评分，如果没有则使用搜索结果的评分
        rating = 0.0
        if details and details.get('rating'):
            rating = details['rating']
        elif movie_info.get('rating'):
            try:
                rating = float(movie_info['rating'])
            except (ValueError, TypeError):
                rating = 0.0
        
        # 如果没有评分，返回None
        if rating == 0.0:
            return None
        
        votes = details.get('votes', '') if details else ''
        
        summary_parts = []
        if votes:
            summary_parts.append(f"{votes} 人评价")
        
        if details and details.get('director'):
            summary_parts.append(f"导演: {details['director']}")
        
        if details and details.get('year'):
            summary_parts.append(f"年份: {details['year']}")
        
        local_title = details.get('title') if details else movie_info.get('title')

        # 如果从详情页没有获取到信息，使用搜索结果中的信息
        if not summary_parts and movie_info.get('info'):
            info_text = movie_info['info']
            # 提取年份
            year_match = re.search(r'(\d{4})', info_text)
            if year_match:
                summary_parts.append(f"年份: {year_match.group(1)}")
        
        if local_title and local_title not in summary_parts:
            summary_parts.insert(0, local_title)
        
        summary = " | ".join(summary_parts) if summary_parts else "豆瓣评分"
        
        # 计算置信度
        confidence = 0.6  # 基础置信度（搜索结果的评分）
        if details and details.get('votes') and '人' in details['votes']:
            confidence += 0.2  # 有评价人数加分
        if details and details.get('director'):
            confidence += 0.1  # 有导演信息加分
        if details:  # 如果成功获取到详情页信息
            confidence += 0.1
       
        return RatingResult(
            source=self.source,
            score=rating,
            scale=10.0,
            url=movie_info['url'],
            summary=summary,
            confidence=min(confidence, 1.0),
            local_title=local_title,
        )
