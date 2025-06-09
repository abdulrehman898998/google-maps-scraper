import asyncio
import logging
import os
import random
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from supabase import create_client, Client
from urllib.parse import quote
from twocaptcha import TwoCaptcha
from twocaptcha.api import ApiException

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Environment variables
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
TWOCAPTCHA_API_KEY = os.getenv("TWOCAPTCHA_API_KEY")
PROXY_SERVER = os.getenv("PROXY_SERVER", "")
PROXY_USERNAME = os.getenv("PROXY_USERNAME", "")
PROXY_PASSWORD = os.getenv("PROXY_PASSWORD", "")

# Initialize Supabase client
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    logger.error(f"Failed to initialize Supabase client: {e}")
    raise

# Initialize 2Captcha client
twocaptcha = TwoCaptcha(TWOCAPTCHA_API_KEY) if TWOCAPTCHA_API_KEY else None

# Queries
QUERIES = [
    {"query": "furniture store in 93307"},
    {"query": "furniture store in 92503"},
    {"query": "furniture store in 10456"},
    {"query": "furniture store in 78613"},
    {"query": "furniture store in 30043"}
]

# Proxy settings
PROXY = {
    "server": PROXY_SERVER,
    "username": PROXY_USERNAME,
    "password": PROXY_PASSWORD
} if PROXY_SERVER else {}

async def solve_captcha(page):
    if not twocaptcha:
        logger.error("2Captcha API key not provided")
        return False
    try:
        logger.info("Attempting to solve CAPTCHA")
        # Detect CAPTCHA (e.g., reCAPTCHA checkbox)
        captcha = await page.query_selector('div[aria-label*="CAPTCHA"]') or \
                 await page.query_selector('iframe[src*="recaptcha"]')
        if not captcha:
            logger.info("No CAPTCHA detected")
            return True

        # Get sitekey from reCAPTCHA iframe
        sitekey = await page.evaluate('''() => {
            const iframe = document.query_selector('iframe[src*="recaptcha"]');
            return iframe ? iframe.src.match(/k=([^&]+)/)?.[1] : null;
        }''')
        if not sitekey:
            logger.error("Could not find CAPTCHA sitekey")
            return False

        # Solve CAPTCHA with 2Captcha
        result = twocaptcha.recaptcha(
            sitekey=sitekey,
            url=page.url,
            proxy=PROXY if PROXY.get("server") else None
        )
        code = result['code']
        logger.info("CAPTCHA solved successfully")

        # Inject CAPTCHA response
        await page.evaluate(f'''() => {{
            document.getElementById('g-recaptcha-response').innerText = "{code}";
            grecaptcha.execute();
        }}''')
        await asyncio.sleep(2)  # Wait for submission
        return True
    except ApiException as e:
        logger.error(f"2Captcha error: {e}")
        return False
    except Exception as e:
        logger.error(f"Error solving CAPTCHA: {e}")
        return False

async def scrape_google_maps(query, page):
    results = []
    try:
        logger.info(f"Processing query: {query}")
        
        # Encode query for URL
        encoded_query = quote(query)
        url = f"https://www.google.com/maps/search/{encoded_query}/"
        
        # Navigate to Google Maps
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
        except PlaywrightTimeoutError:
            logger.warning(f"Timeout navigating to {url}, retrying after CAPTCHA check")
            if await solve_captcha(page):
                await page.goto(url, wait_until="networkidle", timeout=30000)
            else:
                logger.error(f"Failed to solve CAPTCHA for {query}")
                return results

        logger.info(f"Loaded Google Maps for query: {query}")

        # Check for CAPTCHA
        if await page.query_selector('div[aria-label*="CAPTCHA"]') or \
           await page.query_selector('iframe[src*="recaptcha"]'):
            logger.info("CAPTCHA detected, attempting to solve")
            if not await solve_captcha(page):
                logger.error(f"Failed to solve CAPTCHA for {query}")
                return results

        # Wait for search results
        try:
            await page.wait_for_selector('div[role="main"]', timeout=10000)
        except PlaywrightTimeoutError:
            logger.error(f"Search results not found for {query}")
            return results

        # Scroll to load more results
        async def scroll_results():
            last_height = await page.evaluate("document.querySelector('div[role=\"main\"]').scrollHeight")
            for _ in range(3):
                await page.evaluate("document.querySelector('div[role=\"main\"]').scrollTo(0, document.querySelector('div[role=\"main\"]').scrollHeight)")
                await asyncio.sleep(2)
                new_height = await page.evaluate("document.querySelector('div[role=\"main\"]').scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height

        await scroll_results()

        # Extract business listings
        listings = await page.query_selector_all('div[role="article"]')
        logger.info(f"Found {len(listings)} listings for query: {query}")

        for listing in listings[:10]:  # Limit to top 10 results
            try:
                # Click on listing to load details
                await listing.click()
                await asyncio.sleep(1)

                # Extract details with fallback
                name = await page.evaluate('''() => {
                    const el = document.querySelector('h1');
                    return el ? el.innerText : "";
                }''') or "N/A"

                address = await page.evaluate('''() => {
                    const el = document.querySelector('button[data-item-id*="address"]') || 
                              document.querySelector('div[data-tooltip*="Address"]');
                    return el ? el.innerText : "";
                }''') or "N/A"

                website = await page.evaluate('''() => {
                    const el = document.querySelector('a[data-item-id*="authority"]') || 
                              document.querySelector('a[href*="http"]');
                    return el ? el.getAttribute("href") : "";
                }''') or "N/A"

                phone = await page.evaluate('''() => {
                    const el = document.querySelector('button[data-item-id*="phone"]') || 
                              document.querySelector('div[data-tooltip*="Phone"]');
                    return el ? el.innerText : "";
                }''') or "N/A"

                rating = await page.evaluate('''() => {
                    const el = document.querySelector('span[aria-label*="stars"]') || 
                              document.querySelector('div[role="img"][aria-label*="stars"]');
                    return el ? el.innerText.split(" ")[0] : "";
                }''') or "N/A"

                result = {
                    "query": query,
                    "name": name,
                    "address": address,
                    "website": website,
                    "phone": phone,
                    "rating": rating
                }
                results.append(result)
                logger.info(f"Scraped: {name}")

                # Insert into Supabase with retry
                for attempt in range(3):
                    try:
                        supabase.table("leads").insert(result).execute()
                        logger.info(f"Inserted {name} into Supabase")
                        break
                    except Exception as e:
                        logger.error(f"Attempt {attempt + 1} failed to insert {name} into Supabase: {e}")
                        if attempt == 2:
                            logger.error(f"Failed to insert {name} after 3 attempts")
                        await asyncio.sleep(2)

            except Exception as e:
                logger.error(f"Error scraping listing for query {query}: {e}")
                continue

    except PlaywrightTimeoutError:
        logger.error(f"Timeout error for query: {query}")
    except Exception as e:
        logger.error(f"Error processing query {query}: {e}")

    return results

async def main():
    async with async_playwright() as p:
        # Set up browser with proxy
        browser_args = {
            "headless": True,
            "args": ["--no-sandbox", "--disable-setuid-sandbox"]
        }
        if PROXY.get("server"):
            browser_args["proxy"] = PROXY

        try:
            browser = await p.chromium.launch(**browser_args)
        except Exception as e:
            logger.error(f"Failed to launch browser: {e}")
            return

        # Rotate user-agents
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.101 Safari/537.36"
        ]
        context = await browser.new_context(
            user_agent=random.choice(user_agents),
            viewport={"width": 1280, "height": 720}
        )
        page = await context.new_page()

        # Process all queries
        for query_dict in QUERIES:
            await scrape_google_maps(query_dict["query"], page)
            await asyncio.sleep(random.uniform(3, 7))  # Random delay

        await browser.close()
        logger.info("Scraping completed")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"Main execution failed: {e}")
