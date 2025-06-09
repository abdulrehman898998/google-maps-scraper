import asyncio
import logging
import os
import random
import time
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from supabase import create_client, Client
from urllib.parse import quote

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Your Supabase credentials
SUPABASE_URL = "https://gbrcgpzdemwtntaafopx.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImdicmNncHpkZW13dG50YWFmb3B4Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDkxMTE1NTksImV4cCI6MjA2NDY4NzU1OX0.AwQYMoKJMNQ3Y6guSsiq9Ur48pNUJOkxujiK8xzuH4A"
TWOCAPTCHA_API_KEY = "b181f81777daef3a34f0f2a4786f0356"

# Optional proxy settings (set these in Railway if needed)
PROXY_SERVER = os.getenv("PROXY_SERVER", "")
PROXY_USERNAME = os.getenv("PROXY_USERNAME", "")
PROXY_PASSWORD = os.getenv("PROXY_PASSWORD", "")

# Initialize Supabase client
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    logger.info("✅ Supabase client initialized successfully")
except Exception as e:
    logger.error(f"❌ Failed to initialize Supabase client: {e}")
    exit(1)

# Initialize 2Captcha client
twocaptcha = None
try:
    from twocaptcha import TwoCaptcha
    from twocaptcha.api import ApiException
    twocaptcha = TwoCaptcha(TWOCAPTCHA_API_KEY)
    logger.info("✅ 2Captcha client initialized successfully")
except ImportError as e:
    logger.error(f"❌ Failed to import 2captcha: {e}")
    logger.error("Make sure 2captcha-python is installed: pip install 2captcha-python")
    exit(1)
except Exception as e:
    logger.error(f"❌ Failed to initialize 2Captcha: {e}")
    exit(1)

# Search queries for furniture stores
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
    """Attempt to solve CAPTCHA using 2Captcha service"""
    try:
        logger.info("🔍 Checking for CAPTCHA...")
        
        # Wait a bit for any CAPTCHA to load
        await asyncio.sleep(3)
        
        # Look for different types of CAPTCHA elements
        captcha_selectors = [
            'iframe[src*="recaptcha"]',
            'div[class*="recaptcha"]',
            '[id*="captcha"]',
            '[class*="captcha"]'
        ]
        
        captcha_element = None
        for selector in captcha_selectors:
            captcha_element = await page.query_selector(selector)
            if captcha_element:
                logger.info(f"🎯 Found CAPTCHA with selector: {selector}")
                break
        
        if not captcha_element:
            logger.info("✅ No CAPTCHA detected")
            return True
        
        # Get the site key for reCAPTCHA
        sitekey = await page.evaluate('''() => {
            // Try multiple ways to find the sitekey
            const iframe = document.querySelector('iframe[src*="recaptcha"]');
            if (iframe && iframe.src) {
                const match = iframe.src.match(/k=([A-Za-z0-9_-]+)/);
                if (match) return match[1];
            }
            
            // Look for data-sitekey attribute
            const elements = document.querySelectorAll('[data-sitekey]');
            for (let el of elements) {
                if (el.getAttribute('data-sitekey')) {
                    return el.getAttribute('data-sitekey');
                }
            }
            
            return null;
        }''')
        
        if not sitekey:
            logger.error("❌ Could not find CAPTCHA sitekey")
            return False
        
        logger.info(f"🔑 Found sitekey: {sitekey[:20]}...")
        
        # Solve CAPTCHA with 2Captcha
        logger.info("🤖 Solving CAPTCHA with 2Captcha...")
        result = twocaptcha.recaptcha(
            sitekey=sitekey,
            url=page.url
        )
        
        captcha_solution = result['code']
        logger.info("✅ CAPTCHA solved successfully!")
        
        # Inject the solution
        await page.evaluate(f'''
            (function() {{
                // Find and fill the response textarea
                const responseArea = document.getElementById('g-recaptcha-response') || 
                                   document.querySelector('[name="g-recaptcha-response"]');
                if (responseArea) {{
                    responseArea.style.display = 'block';
                    responseArea.value = "{captcha_solution}";
                    responseArea.innerHTML = "{captcha_solution}";
                }}
                
                // Trigger the callback if available
                if (typeof grecaptcha !== 'undefined' && grecaptcha.getResponse) {{
                    try {{
                        grecaptcha.execute();
                    }} catch(e) {{
                        console.log('grecaptcha.execute failed:', e);
                    }}
                }}
                
                // Submit any forms that might be waiting
                const forms = document.querySelectorAll('form');
                forms.forEach(form => {{
                    const submitBtn = form.querySelector('[type="submit"]');
                    if (submitBtn) {{
                        submitBtn.click();
                    }}
                }});
            }})();
        ''')
        
        await asyncio.sleep(3)  # Wait for submission
        return True
        
    except ApiException as e:
        logger.error(f"❌ 2Captcha API error: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Error solving CAPTCHA: {e}")
        return False

async def scrape_google_maps(query, page):
    """Scrape Google Maps for business listings"""
    results = []
    
    try:
        logger.info(f"🔍 Processing query: {query}")
        
        # Navigate to Google Maps search
        encoded_query = quote(query)
        url = f"https://www.google.com/maps/search/{encoded_query}/"
        
        logger.info(f"🌐 Navigating to: {url}")
        await page.goto(url, wait_until="networkidle", timeout=30000)
        
        # Check for CAPTCHA
        await solve_captcha(page)
        
        # Wait for search results to load
        try:
            await page.wait_for_selector('div[role="main"]', timeout=20000)
            logger.info("✅ Search results loaded")
        except PlaywrightTimeoutError:
            logger.error("❌ Search results not found - page may be blocked")
            return results
        
        # Scroll to load more results
        logger.info("📜 Scrolling to load more results...")
        for i in range(3):
            await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            await asyncio.sleep(2)
        
        # Find all business listings
        await asyncio.sleep(3)
        listings = await page.query_selector_all('div[role="article"]')
        logger.info(f"📋 Found {len(listings)} potential listings")
        
        # Extract data from each listing
        for i, listing in enumerate(listings[:10]):  # Limit to top 10
            try:
                logger.info(f"📊 Processing listing {i+1}/10...")
                
                # Click on the listing to load details
                await listing.click()
                await asyncio.sleep(3)  # Wait for details to load
                
                # Extract business information
                name = await page.evaluate('''() => {
                    const selectors = ['h1[data-attrid="title"]', 'h1', '[data-attrid="title"]'];
                    for (let sel of selectors) {
                        const el = document.querySelector(sel);
                        if (el && el.innerText.trim()) return el.innerText.trim();
                    }
                    return '';
                }''') or "N/A"
                
                address = await page.evaluate('''() => {
                    const selectors = [
                        'button[data-item-id*="address"]',
                        '[data-item-id*="address"]',
                        '.rogA2c .Io6YTe',
                        '[aria-label*="Address"]'
                    ];
                    for (let sel of selectors) {
                        const el = document.querySelector(sel);
                        if (el && el.innerText.trim()) return el.innerText.trim();
                    }
                    return '';
                }''') or "N/A"
                
                phone = await page.evaluate('''() => {
                    const selectors = [
                        'button[data-item-id*="phone"]',
                        '[data-item-id*="phone"]',
                        '.rogA2c .UsdlK',
                        '[aria-label*="Phone"]'
                    ];
                    for (let sel of selectors) {
                        const el = document.querySelector(sel);
                        if (el && el.innerText.trim()) return el.innerText.trim();
                    }
                    return '';
                }''') or "N/A"
                
                website = await page.evaluate('''() => {
                    const selectors = [
                        'a[data-item-id*="authority"]',
                        'a[href*="http"]:not([href*="google"]):not([href*="maps"])'
                    ];
                    for (let sel of selectors) {
                        const el = document.querySelector(sel);
                        if (el && el.href && !el.href.includes('google') && !el.href.includes('maps')) {
                            return el.href;
                        }
                    }
                    return '';
                }''') or "N/A"
                
                rating = await page.evaluate('''() => {
                    const el = document.querySelector('span[aria-label*="stars"]');
                    if (el && el.getAttribute('aria-label')) {
                        const match = el.getAttribute('aria-label').match(/([0-9.]+)/);
                        return match ? match[1] : '';
                    }
                    return '';
                }''') or "N/A"
                
                # Skip if no name found
                if name in ["N/A", ""]:
                    logger.warning(f"⚠️ Skipping listing {i+1} - no name found")
                    continue
                
                # Create result object
                result = {
                    "query": query,
                    "name": name,
                    "address": address,
                    "phone": phone,
                    "website": website,
                    "rating": rating,
                    "scraped_at": time.strftime("%Y-%m-%d %H:%M:%S")
                }
                
                results.append(result)
                logger.info(f"✅ Scraped: {name}")
                
                # Save to Supabase
                try:
                    supabase.table("leads").insert(result).execute()
                    logger.info(f"💾 Saved {name} to Supabase")
                except Exception as e:
                    logger.error(f"❌ Failed to save {name} to Supabase: {e}")
                
            except Exception as e:
                logger.error(f"❌ Error processing listing {i+1}: {e}")
                continue
    
    except Exception as e:
        logger.error(f"❌ Error processing query '{query}': {e}")
    
    return results

async def main():
    """Main scraper function"""
    logger.info("🚀 Starting Google Maps Scraper...")
    
    async with async_playwright() as p:
        # Browser configuration
        browser_args = {
            "headless": True,
            "args": [
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-web-security",
                "--disable-features=VizDisplayCompositor"
            ]
        }
        
        # Add proxy if configured
        if PROXY.get("server"):
            browser_args["proxy"] = PROXY
            logger.info(f"🌐 Using proxy: {PROXY['server']}")
        
        # Launch browser
        try:
            browser = await p.chromium.launch(**browser_args)
            logger.info("✅ Browser launched successfully")
        except Exception as e:
            logger.error(f"❌ Failed to launch browser: {e}")
            return
        
        # Create browser context
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ]
        
        context = await browser.new_context(
            user_agent=random.choice(user_agents),
            viewport={"width": 1366, "height": 768}
        )
        
        page = await context.new_page()
        
        # Process all queries
        total_results = 0
        for i, query_dict in enumerate(QUERIES, 1):
            logger.info(f"📍 Processing query {i}/{len(QUERIES)}: {query_dict['query']}")
            
            query_results = await scrape_google_maps(query_dict["query"], page)
            total_results += len(query_results)
            
            logger.info(f"✅ Query {i} completed: {len(query_results)} results")
            
            # Random delay between queries to avoid detection
            if i < len(QUERIES):  # Don't delay after the last query
                delay = random.uniform(10, 20)
                logger.info(f"⏳ Waiting {delay:.1f} seconds before next query...")
                await asyncio.sleep(delay)
        
        await browser.close()
        logger.info(f"🎉 Scraping completed! Total results: {total_results}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⏹️ Scraping interrupted by user")
    except Exception as e:
        logger.error(f"❌ Main execution failed: {e}")
        exit(1)
