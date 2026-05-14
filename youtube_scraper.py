"""
YouTube Videos Updater Script for Uranium Content

This script updates the VideoPageData table with fresh YouTube videos
by searching for uranium mining, uranium market analysis, and uranium-related content in different categories.
"""

import sys
import os
from datetime import datetime, timedelta
from youtube_search import YoutubeSearch
import logging
import re
import requests

# Add the parent directory to the path to import database_config
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from database_config import get_curser
from database_operations import (
    check_youtube_video_url_exists,
    insert_youtube_video,
    delete_all_youtube_videos
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def clean_views_string(views_str):
    """
    Clean views string and convert to integer.
    
    Args:
        views_str (str): Views string like "10,825 views" or "453 views"
    
    Returns:
        int: Number of views as integer, or None if parsing fails
    """
    try:
        if not views_str:
            return None
        # Remove commas and "views" text, then convert to int
        cleaned = views_str.replace(',', '').replace(' views', '').replace('views', '').strip()
        return int(cleaned) if cleaned.isdigit() else None
    except:
        return None

def parse_youtube_publish_time(publish_time_str):
    """
    Parse YouTube publish time string and convert to date.
    
    Args:
        publish_time_str (str): YouTube publish time like "2 days ago", "1 week ago", etc.
    
    Returns:
        datetime.date: Calculated date based on publish time
    """
    try:
        if not publish_time_str:
            return datetime.now().date()
        
        # Convert to lowercase for easier parsing
        publish_time_str = publish_time_str.lower().strip()
        
        # Extract number and time unit
        if 'hour' in publish_time_str:
            hours = int(re.search(r'(\d+)', publish_time_str).group(1))
            return (datetime.now() - timedelta(hours=hours)).date()
        elif 'day' in publish_time_str:
            days = int(re.search(r'(\d+)', publish_time_str).group(1))
            return (datetime.now() - timedelta(days=days)).date()
        elif 'week' in publish_time_str:
            weeks = int(re.search(r'(\d+)', publish_time_str).group(1))
            return (datetime.now() - timedelta(weeks=weeks)).date()
        elif 'month' in publish_time_str:
            months = int(re.search(r'(\d+)', publish_time_str).group(1))
            return (datetime.now() - timedelta(days=months * 30)).date()
        elif 'year' in publish_time_str:
            years = int(re.search(r'(\d+)', publish_time_str).group(1))
            return (datetime.now() - timedelta(days=years * 365)).date()
        else:
            # If we can't parse it, return current date
            logger.warning(f"Could not parse publish time: {publish_time_str}")
            return datetime.now().date()
            
    except Exception as e:
        logger.error(f"Error parsing publish time '{publish_time_str}': {e}")
        return datetime.now().date()

def validate_thumbnail(thumbnail_url, timeout=3):
    """
    Validate that a thumbnail URL is accessible
    
    Args:
        thumbnail_url (str): The thumbnail URL to validate
        timeout (int): Request timeout in seconds
    
    Returns:
        bool: True if thumbnail is accessible, False otherwise
    """
    try:
        response = requests.head(thumbnail_url, timeout=timeout)
        return response.status_code == 200
    except:
        return False

def search_youtube_videos(query, max_results=10):
    """
    Search YouTube for videos based on a query, prioritizing recent videos.
    
    Args:
        query (str): The search query
        max_results (int): Maximum number of results to return
    
    Returns:
        list: List of video dictionaries sorted by recency
    """
    try:
        logger.info(f"Searching YouTube for: {query}")
        
        # Get more results to filter for recent videos (increased to 5x for strict date filtering)
        search_results = YoutubeSearch(query, max_results=max_results * 5).to_dict()
        
        video_list = []
        for video in search_results:
            # Check if video has thumbnail
            thumbnails = video.get('thumbnails', [])
            if not thumbnails or len(thumbnails) == 0:
                logger.info(f"Skipping video without thumbnail: {video.get('title', 'Unknown')}")
                continue
            
            # Extract video ID from URL to validate thumbnail availability
            url_suffix = video.get('url_suffix', '')
            if '/watch?v=' not in url_suffix:
                logger.info(f"Skipping video with invalid URL: {video.get('title', 'Unknown')}")
                continue
            
            video_id = url_suffix.split('/watch?v=')[1].split('&')[0] if '/watch?v=' in url_suffix else None
            if not video_id or len(video_id) != 11:
                logger.info(f"Skipping video with invalid video ID: {video.get('title', 'Unknown')}")
                continue
            
            # Validate that YouTube thumbnail URL would work
            thumbnail_url = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
            
            video_info = {
                'title': video.get('title', ''),
                'link': f"https://www.youtube.com{url_suffix}",
                'duration': video.get('duration', ''),
                'views': clean_views_string(video.get('views', '')),
                'channel': video.get('channel', ''),
                'publish_time': video.get('publish_time', ''),
                'parsed_date': parse_youtube_publish_time(video.get('publish_time', '')),
                'video_id': video_id,
                'thumbnail_url': thumbnail_url
            }
            
            # Additional validation - skip very short videos (likely ads/shorts without proper thumbnails)
            duration = video.get('duration', '')
            if duration and ':' in duration:
                try:
                    parts = duration.split(':')
                    if len(parts) == 2:  # MM:SS format
                        minutes, seconds = int(parts[0]), int(parts[1])
                        total_seconds = minutes * 60 + seconds
                        if total_seconds < 30:  # Skip videos shorter than 30 seconds
                            logger.info(f"Skipping very short video ({duration}): {video.get('title', 'Unknown')}")
                            continue
                except:
                    pass  # If we can't parse duration, continue anyway
            
            # Check if video is relevant and high quality
            if not is_relevant_video(video.get('title', ''), video.get('channel', ''), duration):
                logger.info(f"Skipping irrelevant/low-quality video: {video.get('title', 'Unknown')}")
                continue
            
            # Check if video is within the last 4 weeks
            parsed_date = parse_youtube_publish_time(video.get('publish_time', ''))
            four_weeks_ago = (datetime.now() - timedelta(weeks=4)).date()
            if parsed_date < four_weeks_ago:
                logger.info(f"Skipping old video ({video.get('publish_time', 'Unknown date')}): {video.get('title', 'Unknown')}")
                continue
            
            video_list.append(video_info)
        
        # Sort by parsed date (most recent first) and limit to max_results
        video_list.sort(key=lambda x: x['parsed_date'], reverse=True)
        
        # Filter to ONLY videos from the last 4 weeks
        four_weeks_ago = (datetime.now() - timedelta(weeks=4)).date()
        fresh_videos = [v for v in video_list if v['parsed_date'] >= four_weeks_ago]
        
        # If we don't have enough fresh videos, get more from search but still filter by 4 weeks
        if len(fresh_videos) < max_results and len(fresh_videos) < len(video_list):
            logger.info(f"Only {len(fresh_videos)} videos found within 4 weeks, all older videos will be excluded")
        
        final_videos = fresh_videos[:max_results]
        
        logger.info(f"Found {len(final_videos)} valid videos for query: {query}")
        logger.info(f"All videos are within 4 weeks: {len(final_videos)}")
        
        return final_videos
        
    except Exception as e:
        logger.error(f"Error searching YouTube for '{query}': {e}")
        return []

def is_relevant_video(title, channel, duration):
    """
    Check if video is relevant to lithium content and has good quality indicators
    
    Args:
        title (str): Video title
        channel (str): Channel name
        duration (str): Video duration
    
    Returns:
        bool: True if video is relevant and high quality
    """
    text = (title + ' ' + channel).lower()
    
    # Must contain uranium-related keywords
    required_keywords = [
        'uranium', 'uranium mining', 'uranium price', 'uranium market', 'uranium stocks',
        'uranium futures', 'uranium investment', 'nuclear energy', 'nuclear power',
        'mining', 'commodity', 'metal prices', 'uranium demand', 'uranium supply',
        'uranium oxide', 'yellowcake', 'u3o8', 'nuclear fuel', 'enrichment',
        'cameco', 'kazatomprom', 'sprott uranium', 'uranium etf'
    ]
    
    # Exclude irrelevant content
    exclude_keywords = [
        'music', 'song', 'album', 'concert', 'gaming', 'game', 'movie', 'film',
        'recipe', 'cooking', 'fashion', 'beauty', 'sports', 'football', 'basketball',
        'unboxing', 'reaction', 'prank', 'challenge', 'tiktok', 'shorts compilation',
        'uranium battery diy', 'phone battery', 'laptop battery',
        'battery replacement', 'battery mod', 'battery hack'
    ]
    
    # Exclude channels that are likely to have low-quality content
    exclude_channels = [
        'music', 'entertainment', 'gaming', 'kids', 'cartoon', 'anime',
        'reaction', 'compilation', 'funny', 'meme', 'diy', 'crafts'
    ]
    
    has_required = any(keyword in text for keyword in required_keywords)
    has_excluded = any(keyword in text for keyword in exclude_keywords)
    has_excluded_channel = any(keyword in channel.lower() for keyword in exclude_channels)
    
    # Additional quality checks
    if duration:
        try:
            # Parse duration and exclude very long videos (likely streams) or very short ones
            parts = duration.split(':')
            if len(parts) == 2:  # MM:SS format
                minutes = int(parts[0])
                if minutes > 120:  # Exclude videos longer than 2 hours
                    return False
                if minutes < 1:  # Exclude videos shorter than 1 minute
                    return False
        except:
            pass
    
    return has_required and not has_excluded and not has_excluded_channel

def extract_company_info(title, channel):
    """
    Extract company name and stock ticker from video title and channel.
    
    Args:
        title (str): Video title
        channel (str): Channel name
    
    Returns:
        tuple: (company_name, stock_ticker)
    """
    # Common uranium companies and their tickers
    companies = {
        # Major Producers
        'cameco': {'name': 'Cameco Corporation', 'ticker': 'CCJ'},
        'kazatomprom': {'name': 'Kazatomprom', 'ticker': 'KAP'},
        'paladin energy': {'name': 'Paladin Energy', 'ticker': 'PDN.AX'},
        'nexgen energy': {'name': 'NexGen Energy', 'ticker': 'NXE'},
        'denison mines': {'name': 'Denison Mines', 'ticker': 'DNN'},
        'uranium energy': {'name': 'Uranium Energy Corp', 'ticker': 'UEC'},
        'energy fuels': {'name': 'Energy Fuels', 'ticker': 'UUUU'},
        'encore energy': {'name': 'enCore Energy', 'ticker': 'EU'},
        'boss energy': {'name': 'Boss Energy', 'ticker': 'BOE.AX'},
        'yellow cake': {'name': 'Yellow Cake plc', 'ticker': 'YCA.L'},
        # ETFs
        'sprott uranium': {'name': 'Sprott Uranium Miners ETF', 'ticker': 'URNM'},
        'global x uranium': {'name': 'Global X Uranium ETF', 'ticker': 'URA'},
        'vaneck uranium': {'name': 'VanEck Uranium+Nuclear Energy ETF', 'ticker': 'NLR'},
    }
    
    text = (title + ' ' + channel).lower()
    
    for key, info in companies.items():
        if key in text:
            return info['name'], info['ticker']
    
    return None, None

def scrape_youtube_videos():
    """
    Main function to scrape YouTube videos for lithium content.
    Returns a list of videos organized by category.
    """
    logger.info("=" * 60)
    logger.info("Starting YouTube Videos Scraping for Lithium Content")
    logger.info("=" * 60)
    
    # Define search queries for each category (multiple queries per category for better results)
    search_queries = {
        'Featured': [
            'uranium market analysis',
            'uranium price forecast',
            'uranium investment outlook',
            'uranium stocks 2024',
            'uranium demand supply',
            'nuclear energy investment'
        ],
        'Company': [
            'uranium mining stocks',
            'Cameco uranium news',
            'Sprott uranium ETF',
            'Kazatomprom uranium',
            'uranium mining companies',
            'uranium stock analysis'
        ],
        'Podcast': [
            'uranium market podcast',
            'nuclear energy podcast',
            'mining podcast',
            'commodity trading podcast',
            'uranium investment interview',
            'nuclear fuel podcast'
        ],
        'Education': [
            'what is uranium mining',
            'how uranium is mined',
            'uranium uses nuclear',
            'uranium market explained',
            'uranium investment guide',
            'nuclear fuel cycle explained',
            'yellowcake uranium explained'
        ]
    }
    
    all_videos = {}
    
    try:
        # Search and collect videos for each category
        for category, queries in search_queries.items():
            logger.info(f"\nProcessing category: {category}")
            
            all_videos_for_category = []
            
            # Search using multiple queries for this category
            for query in queries:
                logger.info(f"  Searching with query: '{query}'")
                videos = search_youtube_videos(query, max_results=5)  # Reduced per query since we have multiple
                all_videos_for_category.extend(videos)
            
            if all_videos_for_category:
                # Remove duplicates based on video link
                unique_videos = []
                seen_urls = set()
                for video in all_videos_for_category:
                    if video['link'] not in seen_urls:
                        unique_videos.append(video)
                        seen_urls.add(video['link'])
                
                # Limit to max 8 videos per category
                final_videos = unique_videos[:8]
                all_videos[category] = final_videos
                
                logger.info(f"  Total unique videos for {category}: {len(final_videos)}")
            else:
                logger.warning(f"No videos found for category '{category}'")
                all_videos[category] = []
        
        total_videos = sum(len(videos) for videos in all_videos.values())
        logger.info("=" * 60)
        logger.info(f"YouTube Videos Scraping Complete!")
        logger.info(f"Total videos scraped: {total_videos}")
        logger.info("=" * 60)
        
        return all_videos
        
    except Exception as e:
        logger.error(f"Fatal error during YouTube videos scraping: {e}")
        raise

def main():
    """
    Main function to run the YouTube scraper and insert into database
    """
    try:
        # Get database connection
        connection, cursor = get_curser()
        logger.info("Connected to database successfully")
        
        # Delete old videos
        logger.info("Deleting old videos...")
        deleted_count = delete_all_youtube_videos(cursor, connection)
        
        # Scrape new videos
        all_videos = scrape_youtube_videos()
        
        # Insert videos into database
        total_inserted = 0
        for category, videos in all_videos.items():
            if videos:
                logger.info(f"\nInserting videos for category: {category}")
                inserted_count = 0
                
                for video in videos:
                    try:
                        # Check if video already exists
                        if check_youtube_video_url_exists(cursor, video['link']):
                            logger.info(f"Video already exists, skipping: {video['title'][:50]}...")
                            continue
                        
                        # Extract company information
                        company_name, stock_ticker = extract_company_info(
                            video['title'], 
                            video['channel']
                        )
                        
                        # Insert video using the database operations function
                        success = insert_youtube_video(
                            cursor=cursor,
                            connection=connection,
                            video_category=category,
                            video_link=video['link'],
                            channel_name=video['channel'],
                            date=video['parsed_date'],
                            title=video['title'],
                            company_name=company_name,
                            stock_ticker=stock_ticker,
                            thumbnail_url=video.get('thumbnail_url'),
                            duration=video.get('duration'),
                            views=video.get('views'),
                            video_id=video.get('video_id')
                        )
                        
                        if success:
                            inserted_count += 1
                        
                    except Exception as e:
                        logger.warning(f"Failed to insert video '{video['title'][:50]}...': {e}")
                        continue
                
                logger.info(f"Inserted {inserted_count} videos for category '{category}'")
                total_inserted += inserted_count
        
        logger.info("=" * 60)
        logger.info(f"YouTube Videos Processing Complete!")
        logger.info(f"Total videos inserted: {total_inserted}")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Script failed: {e}")
        raise
    
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'connection' in locals():
            connection.close()
        logger.info("Database connection closed")

if __name__ == "__main__":
    main()
