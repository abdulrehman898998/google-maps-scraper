Google Maps Scraper
   A Playwright-based Python script to scrape furniture store leads from Google Maps, handle CAPTCHAs with 2Captcha, and store results in Supabase.
Setup

Prerequisites:

Supabase account with a leads table
2Captcha account with API key
Railway account
(Optional) Proxy service (e.g., Bright Data)


Supabase Table:
CREATE TABLE leads (
    id SERIAL PRIMARY KEY,
    query TEXT,
    name TEXT,
    address TEXT,
    website TEXT,
    phone TEXT,
    rating TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


Environment Variables:Set in Railway (via web dashboard):

SUPABASE_URL: Your Supabase project URL
SUPABASE_KEY: Your Supabase anon key
TWOCAPTCHA_API_KEY: Your 2Captcha API key
PROXY_SERVER: Proxy server (optional)
PROXY_USERNAME: Proxy username (optional)
PROXY_PASSWORD: Proxy password (optional)



Deployment on Railway

Create Repository:

Create this repository on GitHub.
Add all files and push to main.


Deploy via Railway Web:

Go to railway.app.
New Project > Deploy from GitHub.
Select google-maps-scraper repository.
Add environment variables in the Variables tab.
Deploy the service.


Run the Script:

In the Railway dashboard, go to Deployments > Run Command > worker.


Verify Results:

Check the leads table in Supabase.



Notes

Proxies: Use residential proxies to avoid blocks.
CAPTCHAs: 2Captcha handles reCAPTCHA automatically.
Legal: Scraping may violate Google’s Terms of Service. Use responsibly.

