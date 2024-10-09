# utils.py

from playwright.async_api import async_playwright
import re

playwright = None
browser_type = None

# async def initialize_playwright():
#     global playwright, browser_type
#     if playwright is None:
#         playwright = await async_playwright().start()
#         browser_type = playwright.chromium

# async def get_new_browser_context():
#     global browser_type
#     if browser_type is None:
#         await initialize_playwright()
#     browser = await browser_type.launch(headless=True)
#     context = await browser.new_context()
#     return context

# async def close_playwright():
#     global playwright
#     if playwright:
#         await playwright.stop()
#         playwright = None

# In instagram_service.py

async def extract_shortcode(url):
    context = await get_new_browser_context()
    try:
        page = await context.new_page()
        await page.goto(url)
        current_url = page.url
        shortcode_match = re.search(r'/p/([^/]+)', current_url)
        return shortcode_match.group(1) if shortcode_match else None
    finally:
        await context.close()

def extract_username_tiktok(url):
    match = re.search(r'tiktok\.com/@([a-zA-Z0-9_.-]+)', url)
    return match.group(1) if match else None

def extract_content_id(url):
    patterns = [r'video/(\d+)', r'photo/(\d+)', r'/v/(\d+)', r'/(\d+)(?:\?|$)']
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None