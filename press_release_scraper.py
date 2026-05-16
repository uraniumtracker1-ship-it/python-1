             #!/usr/bin/env python3
"""
Optimized Press Release Scraper - Only 1 press release per ticker
"""

import csv
import time
import logging
import os
import sys
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Import our database functions
from database_config import get_curser
from database_operations import (
    insert_press_release,
    check_press_release_url_exists
)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('press_release_scraper.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

def init_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-software-rasterizer")
    chrome_options.add_argument("--disable-setuid-sandbox")
    chrome_options.add_argument("--window-size=1024,768")

    chrome_bin = os.environ.get("CHROME_BIN", "/usr/bin/chromium-browser")
    chromedriver_path = os.environ.get("CHROMEDRIVER_PATH", "/usr/lib/chromium-browser/chromedriver")

    chrome_options.binary_location = chrome_bin
    service = Service(chromedriver_path)

    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.set_page_load_timeout(30)
    driver.implicitly_wait(5)
    return driver

def load_copper_stocks():
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
                
                # Skip ETFs for press releases
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

def get_yahoo_finance_url(ticker, exchange):
    """Generate Yahoo Finance press release URL for a ticker"""
    exchange_suffixes = {
        'TSX': '.TO',
        'TSX.V': '.V',
        'CSE': '.CN',
        'LSE': '.L',
        'HKEX': '.HK',
        'OTC': '',
        'NYSE': '',
        'NASDAQ': '',
        'NYSE Arca': ''
    }
    
    suffix = exchange_suffixes.get(exchange, '')
    yahoo_ticker = f"{ticker}{suffix}"
    
    return f"https://finance.yahoo.com/quote/{yahoo_ticker}/press-releases/"


def scrape_press_releases_for_ticker(driver, ticker, company_name, exchange, cursor):
    """Optimized scraper - only get 1 press release per ticker"""
    url = get_yahoo_finance_url(ticker, exchange)
    
    try:
        logging.info(f"Scraping {ticker} - {url}")
        
        driver.get(url)
        time.sleep(3)  # Wait for page load
        
        # Look for the stream items using the exact structure from your HTML
        try:
            # Try to find the stream items container
            stream_items = driver.find_elements(By.CSS_SELECTOR, "div.stream-item")
            
            if not stream_items:
                # Fallback selectors
                stream_items = driver.find_elements(By.CSS_SELECTOR, "section[data-testid='storyitem']")
            
            if not stream_items:
                logging.warning(f"No press releases found for {ticker}")
                return []
            
            # Only process the FIRST item (most recent press release)
            first_item = stream_items[0]
            
            # Extract the link and title using the exact HTML structure
            try:
                # Look for the main link with the title
                title_link = first_item.find_element(By.CSS_SELECTOR, "a.subtle-link.fin-size-small.titles")
                article_url = title_link.get_attribute("href")
                
                # Get the title from the h3 element
                title_element = title_link.find_element(By.CSS_SELECTOR, "h3")
                title = title_element.text.strip()
                
                # Validate we have both URL and title
                if not article_url or not title or len(title) < 10:
                    logging.warning(f"Invalid press release data for {ticker}")
                    return []
                
                # Check if already exists in database
                if cursor and check_press_release_url_exists(cursor, article_url):
                    logging.info(f"Press release already exists for {ticker}: {title[:50]}...")
                    return []
                
                # Extract date from the footer
                date = datetime.now().strftime("%Y-%m-%d")  # Default to today
                try:
                    footer = first_item.find_element(By.CSS_SELECTOR, "div.publishing")
                    date_text = footer.text
                    # You could parse the date here if needed (e.g., "14d ago" -> actual date)
                except:
                    pass
                
                # Create press release record
                press_release = {
                    'ticker': ticker,
                    'company_name': company_name,
                    'title': title,
                    'date': date,
                    'url': article_url,
                    'content': title  # Use title as content for speed
                }
                
                logging.info(f"Found press release for {ticker}: {title[:60]}...")
                return [press_release]
                
            except Exception as e:
                logging.warning(f"Error extracting press release data for {ticker}: {e}")
                return []
                
        except Exception as e:
            logging.warning(f"Error finding press releases for {ticker}: {e}")
            return []
        
    except Exception as e:
        logging.error(f"Error scraping {ticker}: {e}")
        return []


def main():
    """Main function to scrape press releases for all copper stocks"""
    logging.info("Starting Optimized Press Release Scraper (1 per ticker)")
    
    # Get database connection
    connection, cursor = get_curser()
    if not connection:
        logging.error("Failed to connect to database")
        return
    
    # Load copper stocks
    stocks = load_copper_stocks()
    if not stocks:
        logging.error("No stocks loaded")
        return
    
    # Initialize WebDriver
    driver = init_driver()
    if not driver:
        logging.error("Failed to initialize WebDriver")
        return
    
    try:
        total_press_releases = 0
        successful_stocks = 0
        
        for i, stock in enumerate(stocks, 1):
            ticker = stock['ticker']
            company_name = stock['company_name']
            exchange = stock['exchange']
            
            logging.info(f"Processing {i}/{len(stocks)}: {ticker}")
            
            try:
                # Scrape press releases for this ticker
                press_releases = scrape_press_releases_for_ticker(
                    driver, ticker, company_name, exchange, cursor
                )
                
                # Insert press releases into database
                for pr in press_releases:
                    insert_press_release(cursor, connection, pr)
                    logging.info(f"Inserted: {pr['title'][:50]}...")
                
                if press_releases:
                    total_press_releases += len(press_releases)
                    successful_stocks += 1
                
                # Minimal delay between requests
                time.sleep(1)
                
            except Exception as e:
                logging.error(f"Error processing {ticker}: {e}")
                continue
        
        logging.info(f"Scraping completed!")
        logging.info(f"Total stocks processed: {len(stocks)}")
        logging.info(f"Stocks with new press releases: {successful_stocks}")
        logging.info(f"Total new press releases scraped: {total_press_releases}")
        
    except Exception as e:
        logging.error(f"Error in main execution: {e}")
    
    finally:
        # Clean up
        if driver:
            driver.quit()
        if cursor:
            cursor.close()
        if connection:
            connection.close()

if __name__ == "__main__":
    main()

