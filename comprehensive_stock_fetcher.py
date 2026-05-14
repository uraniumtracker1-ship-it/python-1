#!/usr/bin/env python3
"""
Comprehensive Stock Fetcher for All 224+ Copper Stocks
Fetches data from Yahoo Finance for all stocks in the CSV and inserts into database
"""

import yfinance as yf
import pandas as pd
from datetime import datetime
import time
import logging
import random
import requests
import json
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from database_config import get_curser
from database_operations import insert_stock_metrics
import csv
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('stock_fetcher.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Enhanced custom mappings for problematic tickers
custom_mappings = {
    'NAM.V': 'NAM.V',
    'IVN.TO': 'IVN.TO', 
    'LZM': 'LZM',
    'NICU': 'NICU.V',
    'BRVO': 'BRVO.V',
    'CNRI': 'CNRI.V',
    'PGE': 'PGE.V',
    'AIR': 'AIR.V',
    'PPP': 'PPP.V',
    'CNC': 'CNC.V',
    'RAMP': 'RAMP.V',
    'SX:CSE': 'SX.CN',
    'GT.V': 'GT.V',
    'ppp': 'PPP.V',
    '0S2J.L': '0S2J.L',
    'JMAT': 'JMAT.L',
    'UMI.BR': 'UMI.BR',
    '4080.T': '4080.T',
    'AGPPF': 'AGPPF',
    'TIHRF': 'TIHRF',
    'CHN': 'CHN.AX',
    'FQVLF': 'FQVLF',
    'GLNCY': 'GLNCY',
    'AAUKF': 'AAUKF',
    'IAURY': 'IAURY'
}

def load_all_stock_data():
    """Load all stock data from CSV file with complete details"""
    stock_data = []
    csv_path = 'uranium_stocks_complete.csv'
    
    if not os.path.exists(csv_path):
        logger.error(f"CSV file not found: {csv_path}")
        return []
    
    try:
        with open(csv_path, 'r', encoding='utf-8') as file:
            csv_reader = csv.DictReader(file)
            
            for row_num, row in enumerate(csv_reader, 1):
                # Clean and validate the row data
                cleaned_row = {}
                for key, value in row.items():
                    # Clean the key and value
                    clean_key = key.strip() if key else ''
                    clean_value = value.strip() if value else ''
                    cleaned_row[clean_key] = clean_value
                
                # Ensure we have required fields
                if cleaned_row.get('Ticker') and cleaned_row.get('Company Name'):
                    stock_data.append(cleaned_row)
                    logger.debug(f"Row {row_num}: {cleaned_row.get('Ticker')} - {cleaned_row.get('Company Name')}")
                else:
                    logger.warning(f"Row {row_num}: Missing required data - Ticker: {cleaned_row.get('Ticker')}, Company: {cleaned_row.get('Company Name')}")
        
        logger.info(f"Successfully loaded {len(stock_data)} stocks from CSV file")
        
        # Log summary by exchange
        exchanges = {}
        for stock in stock_data:
            exchange = stock.get('Stock Exchange', 'Unknown')
            exchanges[exchange] = exchanges.get(exchange, 0) + 1
        
        logger.info("Stock distribution by exchange:")
        for exchange, count in sorted(exchanges.items()):
            logger.info(f"  {exchange}: {count} stocks")
        
        return stock_data
        
    except Exception as e:
        logger.error(f"Error loading CSV file: {e}")
        return []

def map_ticker_symbol(ticker_symbol, exchange):
    """Enhanced ticker symbol mapping for Yahoo Finance format"""
    if not ticker_symbol:
        return None
        
    # Check custom mappings first
    if ticker_symbol in custom_mappings:
        return custom_mappings[ticker_symbol]
    
    # Clean the ticker
    ticker_symbol = ticker_symbol.upper().strip()
    exchange = exchange.upper().strip() if exchange else ''
    
    # Handle special cases
    if ':CSE' in ticker_symbol:
        ticker_symbol = ticker_symbol.replace(':CSE', '')
        exchange = 'CSE'
    
    # Remove existing suffixes to clean the ticker
    suffixes = ['.V', '.TO', '.L', '.AX', '.CN', '.BR', '.T', '.HK']
    for suffix in suffixes:
        if ticker_symbol.endswith(suffix):
            ticker_symbol = ticker_symbol[:-len(suffix)]
            break
    
    # Enhanced exchange mappings
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
    mapped_ticker = ticker_symbol + suffix
    
    logger.debug(f"Mapped {ticker_symbol} ({exchange}) -> {mapped_ticker}")
    return mapped_ticker

def calculate_ytd_return(stock):
    """Calculate year-to-date return for a stock"""
    try:
        current_year = datetime.now().year
        year_start = datetime(current_year, 1, 1)
        hist = stock.history(start=year_start, period="1y")
        
        if len(hist) > 0:
            initial_price = hist.iloc[0]['Close']
            current_price = hist.iloc[-1]['Close']
            if initial_price and current_price and initial_price != 0:
                return ((current_price - initial_price) / initial_price) * 100
        return None
    except Exception as e:
        logger.debug(f"Error calculating YTD return: {str(e)}")
        return None

def clean_numeric_value(value_str):
    """Clean numeric string values for database insertion (remove $, commas, convert B/M/K to numbers)"""
    if value_str is None or value_str == '':
        return None
    
    try:
        # Remove $ and % symbols
        cleaned = str(value_str).replace('$', '').replace('%', '').replace(',', '').strip()
        
        # Handle B/M/K suffixes
        multiplier = 1
        if cleaned.endswith('B'):
            multiplier = 1_000_000_000
            cleaned = cleaned[:-1]
        elif cleaned.endswith('M'):
            multiplier = 1_000_000
            cleaned = cleaned[:-1]
        elif cleaned.endswith('K'):
            multiplier = 1_000
            cleaned = cleaned[:-1]
        
        # Convert to float and apply multiplier
        return float(cleaned) * multiplier
    except (ValueError, AttributeError):
        return None

def format_market_cap(value):
    """Format market cap values into B/M/K notation"""
    if isinstance(value, (int, float)) and value > 0:
        if value >= 1e9:
            return f"${value/1e9:.2f}B"
        elif value >= 1e6:
            return f"${value/1e6:.2f}M"
        elif value >= 1e3:
            return f"${value/1e3:.2f}K"
        else:
            return f"${value:.2f}"
    return None

def format_price(value):
    """Format price values"""
    if isinstance(value, (int, float)) and value > 0:
        return f"${value:.2f}"
    return None

def format_percentage(value):
    """Format percentage values"""
    if isinstance(value, (int, float)):
        return f"{value:.2f}%"
    return None

def format_volume(value):
    """Format volume values"""
    if isinstance(value, (int, float)) and value > 0:
        return f"{value:,}"
    return None

def get_stock_info_comprehensive(ticker_symbol, exchange, max_retries=3):
    """Comprehensive stock information fetching with yfinance 1.0 and curl-cffi"""
    yahoo_ticker = map_ticker_symbol(ticker_symbol, exchange)
    
    if not yahoo_ticker:
        logger.warning(f"Could not map ticker {ticker_symbol} on {exchange}")
        return {key: None for key in ['Market Cap', 'Last Price', 'Intraday %', 'Volume',
                                    'YTD %', 'Week 52 Low', 'Week 52 High']}
    
    logger.info(f"Processing {ticker_symbol} -> {yahoo_ticker}")
    
    for attempt in range(max_retries):
        try:
            # Only delay on retries, not on first attempt
            if attempt > 0:
                wait_time = attempt * 2  # Simple linear backoff only for retries
                logger.info(f"Retry delay: {wait_time}s before attempt {attempt + 1}")
                time.sleep(wait_time)
            
            # Create yfinance ticker object (yfinance 1.0 with curl-cffi)
            stock = yf.Ticker(yahoo_ticker)
            logger.debug(f"Attempt {attempt + 1}: Fetching data for {yahoo_ticker}")
            
            # Get stock info - yfinance 1.0 is more reliable
            info = stock.info
            
            # Validate we got meaningful data
            if not info or len(info) < 3:
                raise ValueError(f"Insufficient data received for {yahoo_ticker}")
            
            # Extract and format all the data
            market_cap = format_market_cap(info.get('marketCap'))
            current_price = info.get('currentPrice', info.get('regularMarketPrice'))
            last_price = format_price(current_price)
            
            # Calculate intraday percentage
            prev_close = info.get('regularMarketPreviousClose')
            intraday = None
            if prev_close and current_price and prev_close != 0:
                intraday = ((current_price - prev_close) / prev_close) * 100
            intraday_percentage = format_percentage(intraday)
            
            # Get volume
            volume = format_volume(info.get('volume', info.get('regularMarketVolume')))
            
            # Calculate YTD return
            ytd = calculate_ytd_return(stock)
            ytd_percentage = format_percentage(ytd)
            
            # Get 52-week high/low
            week_52_low = format_price(info.get('fiftyTwoWeekLow'))
            week_52_high = format_price(info.get('fiftyTwoWeekHigh'))
            
            result = {
                'Market Cap': market_cap,
                'Last Price': last_price,
                'Intraday %': intraday_percentage,
                'Volume': volume,
                'YTD %': ytd_percentage,
                'Week 52 Low': week_52_low,
                'Week 52 High': week_52_high
            }
            
            logger.info(f"✅ Successfully fetched data for {ticker_symbol}: Price={last_price}, MCap={market_cap}")
            return result
            
        except Exception as e:
            error_msg = str(e)
            logger.warning(f"Attempt {attempt + 1} failed for {ticker_symbol}: {error_msg}")
            
            # Handle specific error types
            if "404" in error_msg or "Not Found" in error_msg:
                logger.warning(f"Stock {yahoo_ticker} not found on Yahoo Finance")
                break
            
            if attempt == max_retries - 1:
                logger.error(f"❌ Failed after {max_retries} attempts for {ticker_symbol}")
    
    # Return empty data if all attempts failed
    return {key: None for key in ['Market Cap', 'Last Price', 'Intraday %', 'Volume',
                                'YTD %', 'Week 52 Low', 'Week 52 High']}

def process_all_stocks():
    """Process all 224+ stocks from CSV and insert into database"""
    logger.info("🚀 Starting comprehensive stock data processing...")
    
    # Load all stock data from CSV
    stock_data = load_all_stock_data()
    
    if not stock_data:
        logger.error("❌ No stock data loaded from CSV. Exiting.")
        return
    
    # Get database connection
    try:
        connection, cursor = get_curser()
        logger.info("✅ Successfully connected to database")
    except Exception as e:
        logger.error(f"❌ Failed to connect to database: {e}")
        return
    
    # Processing statistics
    total_stocks = len(stock_data)
    processed = 0
    successful = 0
    failed = 0
    
    # Process stocks in larger batches (no rate limiting issues with yfinance 1.0)
    batch_size = 10
    
    logger.info(f"📊 Processing {total_stocks} stocks in batches of {batch_size}")
    logger.info("=" * 80)
    
    try:
        for batch_start in range(0, total_stocks, batch_size):
            batch_end = min(batch_start + batch_size, total_stocks)
            batch_num = (batch_start // batch_size) + 1
            total_batches = (total_stocks + batch_size - 1) // batch_size
            
            logger.info(f"\n🔄 Batch {batch_num}/{total_batches}: Processing stocks {batch_start+1}-{batch_end}")
            
            # Process each stock in the batch
            for i in range(batch_start, batch_end):
                stock_row = stock_data[i]
                processed += 1
                
                # Extract stock information from CSV
                ticker = stock_row.get('Ticker', '').strip()[:50]
                company_name = stock_row.get('Company Name', '').strip()[:100]
                exchange = stock_row.get('Stock Exchange', '').strip()[:50]
                domiciled = stock_row.get('Domiciled', '').strip()[:50]
                mine_location_country = stock_row.get('Mine Location Country', '').strip()
                mine_location_state = stock_row.get('Mine Location State', '').strip()
                company_type = stock_row.get('Company_Type', '').strip()[:50]
                primary_assets = stock_row.get('Primary_Assets', '').strip()[:50]
                secondary_assets = stock_row.get('Secondary_Assets', '').strip()[:50]
                notes = stock_row.get('Notes', '').strip()[:50]
                
                # Combine mine location info (truncate to 50 chars for database)
                mine_location = mine_location_country
                if mine_location_state:
                    mine_location += f", {mine_location_state}"
                # Truncate to 50 characters to fit database constraint
                mine_location = mine_location[:50] if mine_location else None
                
                logger.info(f"\n📈 [{processed}/{total_stocks}] {company_name} ({ticker})")
                logger.info(f"   Exchange: {exchange} | Type: {company_type} | Location: {domiciled}")
                
                if not ticker or not company_name:
                    logger.warning(f"   ⚠️  Skipping due to missing ticker or company name")
                    failed += 1
                    continue
                
                # Fetch stock metrics from Yahoo Finance
                stock_info = get_stock_info_comprehensive(ticker, exchange)
                
                # Insert into database
                try:
                    # Clean numeric values before insertion
                    insert_stock_metrics(
                        cursor=cursor,
                        connection=connection,
                        ticker=ticker,
                        company_name=company_name,
                        stock_type=company_type,
                        exchange=exchange,
                        domiciled=domiciled,
                        mine_location=mine_location,
                        primary_resource=primary_assets,
                        pureplay=notes,
                        market_cap=clean_numeric_value(stock_info['Market Cap']),
                        last_price=clean_numeric_value(stock_info['Last Price']),
                        intraday_percentage=clean_numeric_value(stock_info['Intraday %']),
                        volume=clean_numeric_value(stock_info['Volume']),
                        ytd_percentage=clean_numeric_value(stock_info['YTD %']),
                        week_52_low=clean_numeric_value(stock_info['Week 52 Low']),
                        week_52_high=clean_numeric_value(stock_info['Week 52 High'])
                    )
                    successful += 1
                    logger.info(f"   ✅ Database updated successfully")
                    
                except Exception as e:
                    logger.error(f"   ❌ Database insertion failed: {e}")
                    failed += 1
                
                # Progress update
                if processed % 10 == 0:
                    success_rate = (successful / processed) * 100
                    logger.info(f"\n📊 Progress: {processed}/{total_stocks} ({success_rate:.1f}% success rate)")
                
                # No delays needed with yfinance 1.0 + curl-cffi
                
                # Progress update
                if processed % 10 == 0:
                    success_rate = (successful / processed) * 100
                    logger.info(f"\n📊 Progress: {processed}/{total_stocks} ({success_rate:.1f}% success rate)")
    
    except KeyboardInterrupt:
        logger.info("\n⚠️  Process interrupted by user")
    except Exception as e:
        logger.error(f"\n❌ Unexpected error: {e}")
    finally:
        # Final statistics
        logger.info("\n" + "=" * 80)
        logger.info("📊 FINAL PROCESSING STATISTICS")
        logger.info("=" * 80)
        logger.info(f"Total stocks processed: {processed}")
        logger.info(f"Successfully updated: {successful}")
        logger.info(f"Failed: {failed}")
        if processed > 0:
            success_rate = (successful / processed) * 100
            logger.info(f"Success rate: {success_rate:.1f}%")
        
        # Show database summary
        try:
            cursor.execute("SELECT COUNT(*) FROM api_app_stockmetrics")
            total_in_db = cursor.fetchone()[0]
            logger.info(f"Total records in database: {total_in_db}")
            
            cursor.execute("SELECT COUNT(*) FROM api_app_stockmetrics WHERE last_price IS NOT NULL")
            with_prices = cursor.fetchone()[0]
            logger.info(f"Records with price data: {with_prices}")
            
        except Exception as e:
            logger.error(f"Error getting database statistics: {e}")
        
        # Close database connection
        cursor.close()
        connection.close()
        logger.info("✅ Database connection closed")
        logger.info("🎉 Processing completed!")

if __name__ == "__main__":
    # Set up logging
    logger.info("🚀 Comprehensive Copper Stock Fetcher Starting...")
    logger.info(f"Timestamp: {datetime.now()}")
    
    # Run the comprehensive processing
    process_all_stocks()