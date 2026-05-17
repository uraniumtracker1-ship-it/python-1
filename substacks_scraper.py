import requests
from bs4 import BeautifulSoup
from datetime import datetime
import logging
from database_operations import insert_substack_post, check_substack_url_exists
from database_config import get_curser


# Known uranium-focused Substack newsletters
URANIUM_SUBSTACKS = [
    "https://www.uraniuminsider.com/feed",
    "https://uraniumupdates.substack.com/feed",
    "https://thelodestarnews.substack.com/feed",
    "https://www.nuclearenergyinsider.substack.com/feed",
    "https://substack.com/search/uranium?sort=new&searching=all_posts",
]

def scrape_substack_uranium_posts(cursor=None, max_posts=10):
    """
    Scrapes uranium-related posts from Substack RSS feeds.
    No Selenium needed — RSS is reliable and fast.
    """
    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
    scraped_data = []
    seen_urls = set()

    # 1. Try known uranium Substack RSS feeds directly
    rss_feeds = [
        "https://uraniumupdates.substack.com/feed",
        "https://www.uraniuminsider.com/feed",
        "https://thelodestarnews.substack.com/feed",
        "https://nuclearenergyinsider.substack.com/feed",
        "https://haywood.substack.com/feed",
        "https://kereport.substack.com/feed",
    ]

    for feed_url in rss_feeds:
        if len(scraped_data) >= max_posts:
            break
        try:
            resp = requests.get(feed_url, headers=headers, timeout=15)
            if resp.status_code != 200:
                logging.warning(f"Feed unavailable ({resp.status_code}): {feed_url}")
                continue

            soup = BeautifulSoup(resp.content, "xml")
            items = soup.find_all("item")
            logging.info(f"Feed {feed_url}: found {len(items)} items")

            for item in items:
                if len(scraped_data) >= max_posts:
                    break

                url = item.find("link").text.strip() if item.find("link") else ""
                if not url or url in seen_urls:
                    continue

                # Filter for uranium relevance
                title = item.find("title").text.strip() if item.find("title") else ""
                description = item.find("description").text.strip() if item.find("description") else ""
                combined = (title + " " + description).lower()
                uranium_keywords = ["uranium", "u3o8", "nuclear", "yellowcake", "cameco", "kazatomprom", "enrichment"]
                if not any(kw in combined for kw in uranium_keywords):
                    logging.info(f"Skipping non-uranium post: {title[:50]}")
                    continue

                # Parse date
                date = datetime.now().strftime("%Y-%m-%d")
                pub_date = item.find("pubDate")
                if pub_date:
                    try:
                        date = datetime.strptime(
                            pub_date.text.strip(), "%a, %d %b %Y %H:%M:%S %z"
                        ).strftime("%Y-%m-%d")
                    except:
                        pass

                # Strip HTML from content
                content_raw = description
                content_soup = BeautifulSoup(content_raw, "html.parser")
                content = content_soup.get_text(separator=" ").strip()

                # Image URL
                image_url = ""
                enclosure = item.find("enclosure")
                if enclosure and "image" in enclosure.get("type", ""):
                    image_url = enclosure.get("url", "")
                if not image_url:
                    img = content_soup.find("img")
                    if img:
                        image_url = img.get("src", "")

                seen_urls.add(url)
                scraped_data.append({
                    "title": title,
                    "url": url,
                    "content": content[:5000],  # Trim very long posts
                    "subtitle": "",
                    "image_url": image_url,
                    "date": date,
                })
                logging.info(f"Scraped: {title[:60]}")

        except Exception as e:
            logging.error(f"Error reading feed {feed_url}: {e}")
            continue

    # 2. Fallback: Substack search via requests (no JS needed for basic results)
    if len(scraped_data) < max_posts:
        try:
            search_url = "https://substack.com/api/v1/search?query=uranium&type=post&sort=new"
            resp = requests.get(search_url, headers=headers, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                posts = data.get("posts", []) or data.get("results", [])
                logging.info(f"Substack API returned {len(posts)} posts")

                for post in posts:
                    if len(scraped_data) >= max_posts:
                        break
                    url = post.get("canonical_url") or post.get("url", "")
                    if not url or url in seen_urls:
                        continue

                    date = datetime.now().strftime("%Y-%m-%d")
                    pub = post.get("post_date") or post.get("published_at", "")
                    if pub:
                        try:
                            date = pub.split("T")[0]
                        except:
                            pass

                    seen_urls.add(url)
                    scraped_data.append({
                        "title": post.get("title", ""),
                        "url": url,
                        "content": post.get("truncated_body_text", "")[:5000],
                        "subtitle": post.get("subtitle", ""),
                        "image_url": post.get("cover_image", ""),
                        "date": date,
                    })
                    logging.info(f"API post: {post.get('title', '')[:60]}")
        except Exception as e:
            logging.error(f"Substack API fallback failed: {e}")

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
