#!/usr/bin/env python3
"""
Main Application - Uranium Stock Data Collection Pipeline
Process-based execution: 
- process1 = stock fetcher
- process2 = press release scraper
- process3 = stock news
- process4 = substack scraper
- process5 = youtube scraper
- process6 = general news scraper
"""

import logging
import sys
import time
from datetime import datetime

# Import our modules
from comprehensive_stock_fetcher import process_all_stocks as run_stock_fetcher
from press_release_scraper import main as run_press_release_scraper
from stock_news import main as run_stock_news_fetcher
from substacks_scraper import scrape_substack_uranium_posts, insert_substack_posts_to_db, ensure_table_exists
from youtube_scraper import main as run_youtube_scraper
from news_scrape import (
    scrape_latest_articles_from_mining_site,
    scrape_mining_review_data,
    scrape_lppm_com_news,
    scrape_miningmx_articles,
    scrape_metaldaily_articles,
    scrape_articles_from_miningweekly
)
from database_config import get_curser
from database_operations import update_process_status, insert_general_news

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('uranium_data_pipeline.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

def get_current_process():
    """Get current process from database"""
    try:
        connection, cursor = get_curser()
        cursor.execute("SELECT current_process FROM process_python1 LIMIT 1")
        result = cursor.fetchone()
        cursor.close()
        connection.close()
        return result[0] if result else "process1"
    except:
        return "process1"

def main():
    """Main pipeline function - runs based on current process"""
    current_process = get_current_process()
    logging.info(f"Current process: {current_process}")
    
    if current_process == "process1":
        # Stock fetcher
        logging.info("STARTING PROCESS 1: STOCK FETCHER")
        connection, cursor = get_curser()
        logging.info("Updating to process2 at start")
        update_process_status(cursor, connection, "process2")
        cursor.close()
        connection.close()
        
        try:
            run_stock_fetcher()
            logging.info("Process 1 completed")
        except Exception as e:
            logging.error(f"Error in process1: {e}")
            
    elif current_process == "process2":
        # Press release scraper
        logging.info("STARTING PROCESS 2: PRESS RELEASE SCRAPER")
        connection, cursor = get_curser()
        logging.info("Updating to process3 at start")
        update_process_status(cursor, connection, "process3")
        cursor.close()
        connection.close()
        
        try:
            run_press_release_scraper()
            logging.info("Process 2 completed")
        except Exception as e:
            logging.error(f"Error in process2: {e}")
            
    elif current_process == "process3":
        # Stock news fetcher
        logging.info("STARTING PROCESS 3: STOCK NEWS FETCHER")
        connection, cursor = get_curser()
        logging.info("Updating to process4 at start")
        update_process_status(cursor, connection, "process4")
        cursor.close()
        connection.close()
        
        try:
            run_stock_news_fetcher()
            logging.info("Process 3 completed")
        except Exception as e:
            logging.error(f"Error in process3: {e}")
            
    elif current_process == "process4":
        # Substack scraper
        logging.info("STARTING PROCESS 4: SUBSTACK SCRAPER")
        connection, cursor = get_curser()
        logging.info("Updating to process5 at start")
        update_process_status(cursor, connection, "process5")
        cursor.close()
        connection.close()
        
        try:
            # Ensure table exists
            connection, cursor = get_curser()
            ensure_table_exists(cursor, connection)
            
            # Scrape Substack posts
            posts = scrape_substack_uranium_posts(cursor, max_posts=10)
            if posts:
                logging.info(f"Found {len(posts)} Substack posts. Inserting into database...")
                insert_substack_posts_to_db(cursor, connection, posts)
            else:
                logging.info("No new Substack posts found")
                
            cursor.close()
            connection.close()
            logging.info("Process 4 completed")
        except Exception as e:
            logging.error(f"Error in process4: {e}")
            
    elif current_process == "process5":
        # YouTube scraper
        logging.info("STARTING PROCESS 5: YOUTUBE SCRAPER")
        connection, cursor = get_curser()
        logging.info("Updating to process6 at start")
        update_process_status(cursor, connection, "process6")
        cursor.close()
        connection.close()
        
        try:
            # Run YouTube video scraper
            run_youtube_scraper()
            logging.info("Process 5 completed")
        except Exception as e:
            logging.error(f"Error in process5: {e}")
            
    elif current_process == "process6":
        # General news scraper
        logging.info("STARTING PROCESS 6: GENERAL NEWS SCRAPER")
        connection, cursor = get_curser()
        logging.info("Updating to process1 at start (cycling back)")
        update_process_status(cursor, connection, "process1")
        cursor.close()
        connection.close()
        
        try:
            connection, cursor = get_curser()
            
            # Scrape from multiple sources
            all_articles = []
            
            # Source 1: Mining.com
            logging.info("Scraping Mining.com...")
            try:
                articles = scrape_latest_articles_from_mining_site(cursor)
                for article in articles:
                    insert_general_news(
                        cursor, connection,
                        source="Mining.com",
                        title=article.get('title'),
                        url=article.get('url'),
                        content=article.get('content'),
                        image_url=article.get('image_url'),
                        date=article.get('date')
                    )
                all_articles.extend(articles)
                logging.info(f"Mining.com: {len(articles)} articles")
            except Exception as e:
                logging.error(f"Error scraping Mining.com: {e}")
            
            # Source 2: Mining Review
            logging.info("Scraping Mining Review...")
            try:
                articles = scrape_mining_review_data(cursor)
                for article in articles:
                    insert_general_news(
                        cursor, connection,
                        source="Mining Review",
                        title=article.get('title'),
                        url=article.get('url'),
                        content=article.get('content'),
                        summary=article.get('summary'),
                        image_url=article.get('image_url'),
                        date=article.get('date')
                    )
                all_articles.extend(articles)
                logging.info(f"Mining Review: {len(articles)} articles")
            except Exception as e:
                logging.error(f"Error scraping Mining Review: {e}")
            
            # Source 3: LPPM.com
            logging.info("Scraping LPPM.com...")
            try:
                articles = scrape_lppm_com_news(cursor)
                for article in articles:
                    insert_general_news(
                        cursor, connection,
                        source="LPPM.com",
                        title=article.get('title'),
                        url=article.get('link'),
                        content=article.get('content'),
                        summary=article.get('summary'),
                        date=article.get('date')
                    )
                all_articles.extend(articles)
                logging.info(f"LPPM.com: {len(articles)} articles")
            except Exception as e:
                logging.error(f"Error scraping LPPM.com: {e}")
            
            # Source 4: MiningMX
            logging.info("Scraping MiningMX...")
            try:
                articles = scrape_miningmx_articles(cursor)
                for article in articles:
                    insert_general_news(
                        cursor, connection,
                        source="MiningMX",
                        title=article.get('title'),
                        url=article.get('url'),
                        image_url=article.get('image_url'),
                        date=article.get('date')
                    )
                all_articles.extend(articles)
                logging.info(f"MiningMX: {len(articles)} articles")
            except Exception as e:
                logging.error(f"Error scraping MiningMX: {e}")
            
            # Source 5: Metals Daily
            logging.info("Scraping Metals Daily...")
            try:
                articles = scrape_metaldaily_articles(cursor)
                for article in articles:
                    insert_general_news(
                        cursor, connection,
                        source="Metals Daily",
                        title=article.get('title'),
                        url=article.get('url'),
                        content=article.get('content'),
                        date=article.get('date')
                    )
                all_articles.extend(articles)
                logging.info(f"Metals Daily: {len(articles)} articles")
            except Exception as e:
                logging.error(f"Error scraping Metals Daily: {e}")
            
            # Source 6: Mining Weekly
            logging.info("Scraping Mining Weekly...")
            try:
                articles = scrape_articles_from_miningweekly(cursor, 'uranium')
                for article in articles:
                    insert_general_news(
                        cursor, connection,
                        source="Mining Weekly",
                        title=article.get('title'),
                        url=article.get('url'),
                        content=article.get('content'),
                        image_url=article.get('image_url'),
                        date=article.get('date')
                    )
                all_articles.extend(articles)
                logging.info(f"Mining Weekly: {len(articles)} articles")
            except Exception as e:
                logging.error(f"Error scraping Mining Weekly: {e}")
            
            logging.info(f"Process 6 completed - Total articles: {len(all_articles)}")
            cursor.close()
            connection.close()
            
        except Exception as e:
            logging.error(f"Error in process6: {e}")
    
    else:
        # Default to process1 if unknown process
        logging.warning(f"Unknown process: {current_process}, defaulting to process1")
        connection, cursor = get_curser()
        update_process_status(cursor, connection, "process1")
        cursor.close()
        connection.close()

if __name__ == "__main__":
    main()

