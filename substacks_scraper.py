import requests
from bs4 import BeautifulSoup
from datetime import datetime
import logging
import json
from database_operations import insert_substack_post, check_substack_url_exists
from database_config import get_curser


URANIUM_SUBSTACKS = [
    "uraniumupdates",
    "thelodestarnews", 
    "nuclearenergyinsider",
    "haywood",
    "kereport",
    "uraniumroyalties",
]

URANIUM_KEYWORDS = ["uranium", "u3o8", "nuclear", "yellowcake", "cameco", 
                    "kazatomprom", "enrichment", "reactor", "sprott"]

def get_headers():
    """Browser-like headers to avoid 403s"""
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://substack.com/",
        "DNT": "1",
    }


def fetch_substack_posts_via_api(subdomain, max_posts=10):
    """
    Fetch posts using Substack's public post API endpoint.
    This is the most reliable method — no auth needed.
    """
    posts = []
    url = f"https://{subdomain}.substack.com/api/v1/posts?limit={max_posts}&offset=0"
    
    try:
        resp = requests.get(url, headers=get_headers(), timeout=15)
        logging.info(f"{subdomain}: API status {resp.status_code}")
        
        if resp.status_code != 200:
            return posts

        data = resp.json()
        for post in data:
            try:
                canonical_url = post.get("canonical_url", "")
                if not canonical_url:
                    slug = post.get("slug", "")
                    canonical_url = f"https://{subdomain}.substack.com/p/{slug}"

                # Parse date
                date = datetime.now().strftime("%Y-%m-%d")
                pub = post.get("post_date") or post.get("published_at", "")
                if pub:
                    date = pub.split("T")[0]

                posts.append({
                    "title": post.get("title", ""),
                    "url": canonical_url,
                    "content": post.get("truncated_body_text", "") or post.get("body_text", ""),
                    "subtitle": post.get("subtitle", "") or "",
                    "image_url": post.get("cover_image", "") or "",
                    "date": date,
                })
            except Exception as e:
                logging.warning(f"Error parsing post from {subdomain}: {e}")
                continue

    except Exception as e:
        logging.error(f"API fetch failed for {subdomain}: {e}")

    return posts


def fetch_substack_search(query="uranium", max_posts=10):
    """
    Use Substack's internal search API directly.
    """
    posts = []
    # Try multiple known API patterns
    endpoints = [
        f"https://substack.com/api/v1/posts/search?query={query}&limit={max_posts}",
        f"https://substack.com/api/v1/search/posts?query={query}&limit={max_posts}&sort=new",
    ]

    for endpoint in endpoints:
        try:
            resp = requests.get(endpoint, headers=get_headers(), timeout=15)
            logging.info(f"Search API {endpoint}: status {resp.status_code}")

            if resp.status_code != 200:
                continue

            data = resp.json()
            logging.info(f"Search API response keys: {list(data.keys()) if isinstance(data, dict) else 'list'}")

            # Handle different response shapes
            items = []
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                items = data.get("posts") or data.get("results") or data.get("items") or []

            for item in items[:max_posts]:
                url = item.get("canonical_url") or item.get("url", "")
                if not url:
                    continue
                date = datetime.now().strftime("%Y-%m-%d")
                pub = item.get("post_date") or item.get("published_at", "")
                if pub:
                    date = pub.split("T")[0]
                posts.append({
                    "title": item.get("title", ""),
                    "url": url,
                    "content": item.get("truncated_body_text", "")[:5000],
                    "subtitle": item.get("subtitle", "") or "",
                    "image_url": item.get("cover_image", "") or "",
                    "date": date,
                })

            if posts:
                logging.info(f"Search API returned {len(posts)} posts")
                break

        except Exception as e:
            logging.error(f"Search endpoint failed ({endpoint}): {e}")
            continue

    return posts


def scrape_substack_uranium_posts(cursor=None, max_posts=10):
    scraped_data = []
    seen_urls = set()

    # Stage 1: fetch from each known uranium Substack via their post API
    for subdomain in URANIUM_SUBSTACKS:
        if len(scraped_data) >= max_posts:
            break
        posts = fetch_substack_posts_via_api(subdomain, max_posts=5)
        logging.info(f"{subdomain}: got {len(posts)} posts from API")

        for post in posts:
            if len(scraped_data) >= max_posts:
                break
            url = post["url"]
            if not url or url in seen_urls:
                continue

            # Uranium relevance filter
            combined = (post["title"] + " " + post["content"]).lower()
            if not any(kw in combined for kw in URANIUM_KEYWORDS):
                logging.info(f"Skipping non-uranium: {post['title'][:50]}")
                continue

            seen_urls.add(url)
            scraped_data.append(post)
            logging.info(f"Scraped: {post['title'][:60]}")

    # Stage 2: Substack search API fallback
    if len(scraped_data) < max_posts:
        logging.info("Trying Substack search API...")
        search_posts = fetch_substack_search("uranium", max_posts=max_posts)
        for post in search_posts:
            if len(scraped_data) >= max_posts:
                break
            if post["url"] not in seen_urls:
                seen_urls.add(post["url"])
                scraped_data.append(post)

    logging.info(f"Total scraped: {len(scraped_data)} posts")
    return scraped_data


def insert_substack_posts_to_db(cursor, connection, posts):
    successful_inserts = 0
    for post in posts:
        try:
            if not check_substack_url_exists(cursor, post["url"]):
                insert_substack_post(cursor=cursor, connection=connection, **post)
                successful_inserts += 1
                logging.info(f"Inserted: {post['title'][:50]}")
            else:
                logging.info(f"Duplicate skipped: {post['title'][:50]}")
        except Exception as e:
            logging.error(f"Error inserting '{post['title'][:50]}': {e}")
    logging.info(f"Inserted {successful_inserts}/{len(posts)} posts")


def ensure_table_exists(cursor, connection):
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_app_lithiumsubstack (
                id VARCHAR(255) PRIMARY KEY,
                title TEXT NOT NULL,
                url TEXT UNIQUE NOT NULL,
                content TEXT,
                subtitle TEXT,
                image_url TEXT,
                date DATE NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        connection.commit()
        logging.info("Table api_app_lithiumsubstack is ready")
    except Exception as e:
        logging.error(f"Error ensuring table exists: {e}")
        raise


if __name__ == "__main__":
    connection, cursor = get_curser()
    try:
        ensure_table_exists(cursor, connection)
        posts = scrape_substack_uranium_posts(cursor)
        if posts:
            insert_substack_posts_to_db(cursor, connection, posts)
        else:
            logging.info("No posts found")
    except Exception as e:
        logging.error(f"Error: {e}")
    finally:
        connection.close()
