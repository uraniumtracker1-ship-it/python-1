from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException
from urllib.parse import urljoin
import os
import time
import random
from selenium.webdriver.common.action_chains import ActionChains
from datetime import datetime
from insert_queries import check_url_exists


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


def scrape_latest_articles_from_mining_site(cursor):
    """
    Scrape the latest articles from the "mining.com" website related to uranium.
    """
    driver = init_driver()
    if not driver:
        return []

    base_url = "https://www.mining.com/?s=uranium"
    all_data = []

    try:
        driver.get(base_url)

        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.inner-content.col-lg-8")))
        links = driver.find_elements(By.CSS_SELECTOR, "div.inner-content.col-lg-8 h2 a")

        urls = [urljoin(base_url, link.get_attribute('href')) for link in links[:4]]

        print(f"Found {len(urls)} article URLs.")

        for url in urls:
            if check_url_exists(cursor, url):
                print(f"URL already exists in the database: {url}")
                continue

            driver.get(url)

            WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, "h1.single-title.mt-4.mb-2")))

            try:
                title = driver.find_element(By.CSS_SELECTOR, "h1.single-title.mt-4.mb-2").text
            except Exception as e:
                print(f"Error finding title on {url}: {e}")
                title = "Title not found"

            try:
                content_elements = driver.find_elements(By.CSS_SELECTOR, "div.post-inner-content.row div.col-lg-8.order-0 > p, div.post-inner-content.row div.col-lg-8.order-0 > h2, div.post-inner-content.row div.col-lg-8.order-0 > h3")
                full_content = "\n\n".join([elem.text for elem in content_elements])
            except Exception as e:
                print(f"Error extracting full content on {url}: {e}")
                full_content = "Content extraction failed"

            try:
                image_url = driver.find_element(By.CSS_SELECTOR, "img.attachment-large.size-large.wp-post-image").get_attribute("src")
            except:
                image_url = None

            try:
                date_text = driver.find_element(By.CSS_SELECTOR, "div.post-meta.mb-4").text
                date_raw = date_text.split("|")[1].strip()
                
                formatted_date = datetime.strptime(date_raw, "%B %d, %Y").strftime("%Y-%m-%d")
            except Exception as e:
                print(f"Error extracting date on {url}: {e}")
                formatted_date = None

            article_content = {
                "url": url,
                "title": title.strip(),
                "content": full_content,
                "image_url": image_url,
                "date": formatted_date
            }

            print("Title:", article_content["title"])
            print("Content preview:", article_content["content"][:200] + "...")  # Print first 200 characters
            print("Image URL:", article_content["image_url"])
            print("Date:", article_content["date"])
            print("-" * 80)
            all_data.append(article_content)
    
    finally:
        driver.quit()

    return all_data


def scrape_mining_review_data(cursor):
    
    driver = init_driver()

    try:

        main_url = "https://www.miningreview.com/?s=uranium&category=&company="
        all_data = []

        driver.get(main_url)
        time.sleep(3)

        article_elements = driver.find_elements(By.CSS_SELECTOR, 'div.header a')
        all_urls = [article.get_attribute('href') for article in article_elements if article.get_attribute('href')]

        if not all_urls:
            print("No article URLs found.")
            return []

        all_urls = all_urls[:4]
        print(f"Found {len(all_urls)} URLs to scrape: {all_urls}")

        for article_url in all_urls:
            if check_url_exists(cursor, article_url):
                print(f"URL already exists in the database: {article_url}")
                continue

            driver.get(article_url)
            time.sleep(3)

            try:
                raw_date = driver.find_element(By.CSS_SELECTOR, 'div.post-date').text.strip() if driver.find_elements(By.CSS_SELECTOR, 'div.post-date') else None
                formatted_date = None
                if raw_date:
                    try:
                        formatted_date = datetime.strptime(raw_date, "%d %B %Y").strftime("%Y-%m-%d")
                    except ValueError:
                        print(f"Error formatting date: {raw_date}")

                data = {
                    "url": article_url,
                    "date": formatted_date,
                    "title": driver.find_element(By.CSS_SELECTOR, 'h1.post-title').text.strip() if driver.find_elements(By.CSS_SELECTOR, 'h1.post-title') else None,
                    "summary": driver.find_element(By.CSS_SELECTOR, 'div.header-summary p').text.strip() if driver.find_elements(By.CSS_SELECTOR, 'div.header-summary p') else None,
                    "image_url": None,
                    "content": ""
                }

                featured_image_elements = driver.find_elements(By.CSS_SELECTOR, 'div.post-featured-image div[style*="background:url"]')
                if featured_image_elements:
                    featured_image_style = featured_image_elements[0].get_attribute('style')
                    if featured_image_style:
                        featured_image_url = featured_image_style.split("url(")[1].split(");")[0].strip()
                        data["featured_image"] = featured_image_url.strip('"')

                content_elements = driver.find_elements(By.CSS_SELECTOR, 'div.column.is-two-thirds-desktop > *')
                content_list = []
                for element in content_elements:
                    if element.tag_name in ['p', 'h2', 'h3', 'h4', 'ul', 'ol']:
                        content_list.append(element.text.strip())
                data["content"] = "\n\n".join(content_list)

                all_data.append(data)

            except Exception as e:
                print(f"Error scraping {article_url}: {e}")

    finally:
        driver.quit()

    return all_data


def human_like_scroll(driver):
    """
    Simulate human-like scrolling on a webpage.

    Args:
        driver (WebDriver): Selenium WebDriver instance.
    """
    total_height = driver.execute_script("return document.body.scrollHeight")
    viewport_height = driver.execute_script("return window.innerHeight")
    scrolls = total_height // viewport_height

    for _ in range(scrolls):
        driver.execute_script(f"window.scrollBy(0, {random.randint(100, 300)});")
        time.sleep(random.uniform(0.5, 1.5))



def scrape_news_item(cursor, driver, item):
    """
    Extract details from a single news item element on lppm.com.

    Args:
        driver (WebDriver): Selenium WebDriver instance.
        item (WebElement): Web element representing a news item.

    Returns:
        dict: A dictionary containing news details (date, title, link, summary, full content).
    """
    date = item.find_element(By.CLASS_NAME, "dte").text
    title = item.find_element(By.TAG_NAME, "h4").text
    link = item.find_element(By.TAG_NAME, "a").get_attribute("href")
    summary = item.find_element(By.CLASS_NAME, "leadIn").text

    if check_url_exists(cursor, link):
        print(f"URL already exists in the database: {link}")
        return None

    driver.get(link)
    time.sleep(random.uniform(3, 5))

    human_like_scroll(driver)

    article_content = driver.find_element(By.CLASS_NAME, "content").text

    return {
        "date": date,
        "title": title,
        "link": link,
        "content": summary,
        "summary": article_content
    }



def scrape_lppm_com_news(cursor):
    """
    Scrape the latest news items from lppm.com.
    """
    driver = init_driver()
    if not driver:
        return []

    url = "https://www.lppm.com/news"
    driver.get(url)
    time.sleep(random.uniform(5, 8))

    all_data = []
    try:
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CLASS_NAME, "item")))

        human_like_scroll(driver)

        items = driver.find_elements(By.CLASS_NAME, "item")[:4]

        for item in items:
            # Move to the element before interacting
            ActionChains(driver).move_to_element(item).perform()
            time.sleep(random.uniform(1, 2))

            news_item = scrape_news_item(cursor, driver, item)

            try:
                if news_item:
                    raw_date = news_item.get('date')
                    formatted_date = datetime.strptime(raw_date, "%d %B %Y").strftime("%Y-%m-%d")
                    news_item['date'] = formatted_date
            except Exception as e:
                print(f"Error formatting date '{raw_date}': {e}")
                news_item['date'] = None

            if news_item:
                all_data.append(news_item)
                print(f"Scraped: {news_item['title']}")

            # Go back to the main page
            driver.back()
            time.sleep(random.uniform(2, 4))

    except Exception as e:
        print(f"An error occurred: {e}")

    finally:
        driver.quit()

    return all_data



def scrape_miningmx_article(url, driver):
    """Scrape details from a single article URL."""
    print(f"Scraping URL: {url}")
    try:
        driver.get(url)
        print(f"Loaded page: {url}")

        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CLASS_NAME, 'entry-title')))

        try:
            title = driver.find_element(By.CSS_SELECTOR, '.td-post-header .entry-title').text.strip()
            print(f"Title found: {title}")
        except Exception as e:
            title = None
            print(f"Title not found: {e}")

        try:
            raw_date = driver.find_element(By.CLASS_NAME, 'entry-date').text.strip()
            print(f"Date found: {raw_date}")
            formatted_date = None
            if raw_date:
                try:
                    formatted_date = datetime.strptime(raw_date, "%B %d, %Y").strftime("%Y-%m-%d")
                except ValueError:
                    print(f"Error formatting date: {raw_date}")
        except Exception as e:
            raw_date = None
            formatted_date = None
            print(f"Date not found: {e}")

        try:
            image_url = driver.find_element(By.CSS_SELECTOR, '.td-post-featured-image img').get_attribute('src')
            print(f"Image URL found: {image_url}")
        except Exception as e:
            image_url = None
            print(f"Image URL not found: {e}")

        article_data = {
            'url': url,
            'title': title,
            'date': formatted_date,
            'image_url': image_url
        }

        return article_data

    except WebDriverException as e:
        print(f"Error occurred while processing URL: {url} - {str(e)}")
        return None


def scrape_miningmx_articles(cursor):
    """Scrape articles from a given base URL."""
    print("Setting up Selenium WebDriver...")

    driver = init_driver()
    print("WebDriver setup complete.")
 
    try:
        base_url = 'https://www.miningmx.com/news/uranium/'
        print(f"Accessing base URL: {base_url}")
        driver.get(base_url)

        print("Waiting for page to load...")
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, '.entry-title.td-module-title a')))
        print("Page loaded successfully.")

        print("Finding article links...")
        anchor_tags = driver.find_elements(By.CSS_SELECTOR, '.entry-title.td-module-title a')

        urls_to_scrape = [anchor.get_attribute('href') for anchor in anchor_tags if anchor.get_attribute('href')]
        print(f"Found {len(urls_to_scrape)} articles to scrape.")

        scraped_data = []

        for url in urls_to_scrape:
            if check_url_exists(cursor, url):
                print(f"URL already exists in the database: {url}")
                continue

            article_data = scrape_miningmx_article(url, driver)
            if article_data:
                scraped_data.append(article_data)

        return scraped_data

    finally:
        print("Closing WebDriver...")
        driver.quit()
        print("WebDriver closed.")


def scrape_metaldaily_articles(cursor):

    driver = init_driver()

    try:

        url = "https://www.metalsdaily.com/news/uranium-news/"

        driver.get(url)

        time.sleep(3)

        news_items = driver.find_elements(By.CSS_SELECTOR, "li a.NewsItem")

        scraped_data = []

        for item in news_items:
            title = item.find_element(By.CSS_SELECTOR, ".Title").text
            heading = item.get_attribute("title")
            raw_date = item.find_element(By.CSS_SELECTOR, ".Date").text
            formatted_date = None
            try:
                formatted_date = datetime.strptime(raw_date, "%d-%m-%y").strftime("%Y-%m-%d")
            except ValueError:
                print(f"Error formatting date: {raw_date}")

            url = item.get_attribute("href")

            if check_url_exists(cursor, url):
                print(f"URL already exists in the database: {url}")
                continue

            scraped_data.append({
                "title": title,
                "content": heading,
                "date": formatted_date,
                "url": url
            })

        return scraped_data

    finally:
        driver.quit()



def scrape_articles_from_miningweekly(cursor, metal_name):

    driver = init_driver()
    if not driver:
        print("Failed to initialize WebDriver for Mining Weekly scraping")
        return []

    try:
        driver.get(f'https://www.miningweekly.com/page/{metal_name}')

        main_section = driver.find_element(By.CSS_SELECTOR, '.d-col-lg-11.d-lg-block.order-lg-2.t-col-md-12.m-col-1')

        articles = main_section.find_elements(By.CSS_SELECTOR, '.card.card-border-none.item-spacing.cm-bg-background')

        scraped_data = []

        for article in articles:
            title_elem = article.find_element(By.CSS_SELECTOR, 'a.card-title') if article.find_elements(By.CSS_SELECTOR, 'a.card-title') else None
            title = title_elem.text if title_elem else None

            link = title_elem.get_attribute('href') if title_elem else None

            if link:
                if check_url_exists(cursor, link):
                    print(f"URL already exists in the database: {link}")
                    continue
            else:
                continue

            author_elem = article.find_element(By.CSS_SELECTOR, 'span.cm-author-name') if article.find_elements(By.CSS_SELECTOR, 'span.cm-author-name') else None

            date_elem = article.find_element(By.CSS_SELECTOR, 'span.cm-last-updated') if article.find_elements(By.CSS_SELECTOR, 'span.cm-last-updated') else None
            raw_date = date_elem.text if date_elem else None
            formatted_date = None

            if raw_date and raw_date != None:
                try:
                    raw_date = raw_date.replace('th', '').replace('st', '').replace('nd', '').replace('rd', '')
                    formatted_date = datetime.strptime(raw_date, "%d %B %Y").strftime("%Y-%m-%d")
                except ValueError:
                    formatted_date = None
            
            # Extract date from URL if not found in the page
            if not formatted_date and link:
                try:
                    # Extract date from URL (format: YYYY-MM-DD at the end)
                    url_date = link.split('-')[-3:]
                    if len(url_date) == 3:
                        year, month, day = url_date
                        if year.isdigit() and month.isdigit() and day.isdigit():
                            formatted_date = f"{year}-{month:0>2}-{day:0>2}"
                except Exception as e:
                    print(f"Failed to extract date from URL {link}: {e}")
                    formatted_date = None

            summary_elem = article.find_element(By.CSS_SELECTOR, 'p.card-text') if article.find_elements(By.CSS_SELECTOR, 'p.card-text') else None
            summary = summary_elem.text if summary_elem else None

            image_elem = article.find_element(By.CSS_SELECTOR, 'img.vjs-img') if article.find_elements(By.CSS_SELECTOR, 'img.vjs-img') else None
            image_url = image_elem.get_attribute('src') if image_elem else None

            scraped_data.append({
                "title": title,
                "url": link,
                "date": formatted_date,
                "content": summary,
                "image_url": image_url
            })

        return scraped_data

    except Exception as e:
        print(f"Error occurred while scraping Mining Weekly site: {str(e)}")
        return []

    finally:
        if driver:
            driver.quit()


