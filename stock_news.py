import yfinance as yf
from database_config import get_curser
from database_operations import insert_stock_news
from insert_queries import check_stock_news_url_exists
from datetime import datetime
import logging
import csv
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_uranium_stocks():
    """Load uranium stock tickers from CSV file"""
    stocks = []
    csv_path = 'uranium_stocks_complete.csv'
    
    try:
        with open(csv_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                ticker = row['Ticker'].strip()
                company_name = row['Company Name'].strip()
                exchange = row['Stock Exchange'].strip()
                
                # Skip ETFs for news fetching
                if 'ETF' in row.get('Company_Type', ''):
                    continue
                    
                stocks.append({
                    'ticker': ticker,
                    'company_name': company_name,
                    'exchange': exchange
                })
        
        logging.info(f"Loaded {len(stocks)} uranium stocks from CSV")
        return stocks
        
    except Exception as e:
        logging.error(f"Error loading uranium stocks: {e}")
        return []

def map_ticker_for_yahoo(ticker, exchange):
    """Map ticker to Yahoo Finance format"""
    # Exchange mappings for Yahoo Finance
    exchange_mappings = {
        'TSXV': '.V',
        'TSX.V': '.V', 
        'TSX': '.TO',
        'NYSE': '',
        'NYSE ARCA': '',
        'NASDAQ': '',
        'LONDON': '.L',
        'LSE': '.L',
        'ASX': '.AX',
        'CNE': '.CN',
        'CSE': '.CN',
        'BRUSSELS': '.BR',
        'TOKYO': '.T',
        'OTC': '',
        'HKEX': '.HK',
        'CBOE': ''
    }
    
    suffix = exchange_mappings.get(exchange, '')
    yahoo_ticker = ticker + suffix
    
    return yahoo_ticker
    
def get_all_stock_news(cursor):
    """
    Fetches the latest news for all tickers from the CSV file.
    Returns a list of news items with ticker information.
    """
    stocks = load_uranium_stocks()
    return_all_news = []
    
    # Process stocks in batches to avoid overwhelming the API
    batch_size = 10
    total_stocks = len(stocks)
    processed = 0
    successful = 0
    failed = 0

    logger.info(f"Processing {total_stocks} stocks for news in batches of {batch_size}")

    for batch_start in range(0, total_stocks, batch_size):
        batch_end = min(batch_start + batch_size, total_stocks)
        batch_num = (batch_start // batch_size) + 1
        total_batches = (total_stocks + batch_size - 1) // batch_size
        
        logger.info(f"Batch {batch_num}/{total_batches}: Processing stocks {batch_start+1}-{batch_end}")
        
        for i in range(batch_start, batch_end):
            stock = stocks[i]
            ticker = stock['ticker']
            company_name = stock['company_name']
            exchange = stock['exchange']
            processed += 1
            
            # Map ticker to Yahoo Finance format
            yahoo_ticker = map_ticker_for_yahoo(ticker, exchange)
            
            try:
                logger.info(f"[{processed}/{total_stocks}] Fetching news for {ticker} -> {yahoo_ticker}")
                stock_obj = yf.Ticker(yahoo_ticker)
                all_news = stock_obj.news
                
                if not all_news:
                    logger.warning(f"No news found for ticker: {ticker}")
                    failed += 1
                    continue

                logger.info(f"Found {len(all_news)} news items for {ticker}")
                
                # Process only first 2 news items per stock to avoid too much data
                news_processed = 0
                for news in all_news[:2]:
                    try:
                        company_news = {
                            "ticker": ticker,
                            "company_name": company_name,
                            "exchange": exchange,
                            "yahoo_ticker": yahoo_ticker
                        }
                        
                        # Handle news content
                        content = news.get("content", {})
                        if not isinstance(content, dict):
                            content = {}
                        
                        company_news["title"] = content.get("title", "No title available")
                        company_news["summary"] = content.get("summary", "No summary available")

                        # Handle date
                        pub_date = content.get("pubDate")
                        if pub_date:
                            try:
                                formatted_date = datetime.strptime(pub_date, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%d")
                                company_news["date"] = formatted_date
                            except ValueError:
                                logger.warning(f"Invalid date format for {ticker}: {pub_date}")
                                company_news["date"] = None
                        else:
                            company_news["date"] = None

                        # Handle thumbnail
                        thumbnail = content.get("thumbnail", {})
                        if isinstance(thumbnail, dict):
                            company_news["image"] = thumbnail.get("originalUrl")
                        else:
                            company_news["image"] = None

                        # Handle URL - Extract the actual URL string from the canonicalUrl dictionary
                        canonical_url = news.get("content", {}).get("canonicalUrl", {})
                        url = canonical_url.get("url") if isinstance(canonical_url, dict) else None
                        if url and not check_stock_news_url_exists(cursor, url):
                            company_news["url"] = url
                            company_news["provider"] = content.get("provider", {}).get("displayName", "Unknown")
                            return_all_news.append(company_news)
                            news_processed += 1
                        
                    except Exception as e:
                        logger.error(f"Error processing news item for {ticker}: {str(e)}")
                        continue
                
                if news_processed > 0:
                    successful += 1
                else:
                    failed += 1
                    
                # Small delay between requests to be respectful to the API
                time.sleep(0.5)

            except Exception as e:
                logger.error(f"Error fetching news for ticker {ticker}: {str(e)}")
                failed += 1
                continue
        
        # Progress update after each batch
        success_rate = (successful / processed) * 100 if processed > 0 else 0
        logger.info(f"Batch {batch_num} completed. Progress: {processed}/{total_stocks} ({success_rate:.1f}% success rate)")
        
        # Small delay between batches
        time.sleep(1)

    logger.info(f"News fetching completed: {successful} successful, {failed} failed out of {processed} stocks")
    return return_all_news

def main():
    """Main function to fetch and insert stock news"""
    logger.info("Starting Stock News Fetcher and Database Insertion")
    
    # Get database connection
    connection, cursor = get_curser()
    if not connection:
        logger.error("Failed to connect to database")
        return
    
    try:
        # Fetch news for all stocks
        all_news = get_all_stock_news(cursor)
        
        logger.info(f"Total news items found: {len(all_news)}")
        
        # Insert news items into database
        inserted_count = 0
        for news in all_news:
            try:
                insert_stock_news(cursor, connection, news)
                inserted_count += 1
            except Exception as e:
                logger.error(f"Error inserting news for {news['ticker']}: {e}")
                continue
        
        logger.info(f"Successfully inserted {inserted_count} news items into database")
        
        # Display first few news items as sample
        for i, news in enumerate(all_news[:3]):  # Show first 3 news items
            logger.info(f"\n--- News Item {i+1} ---")
            logger.info(f"Ticker: {news['ticker']} ({news['yahoo_ticker']})")
            logger.info(f"Company: {news['company_name']}")
            logger.info(f"Title: {news['title'][:100]}...")
            logger.info(f"Date: {news['date']}")
            logger.info(f"Provider: {news['provider']}")
        
        # Summary by ticker
        ticker_counts = {}
        for news in all_news:
            ticker = news['ticker']
            ticker_counts[ticker] = ticker_counts.get(ticker, 0) + 1
        
        logger.info(f"\n--- News Count by Ticker (Top 10) ---")
        sorted_tickers = sorted(ticker_counts.items(), key=lambda x: x[1], reverse=True)
        for ticker, count in sorted_tickers[:10]:
            logger.info(f"{ticker}: {count} news items")
            
    except Exception as e:
        logger.error(f"Error in main execution: {e}")
    
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

if __name__ == "__main__":
    main()
