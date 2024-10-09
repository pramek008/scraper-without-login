from app.utils.utils import extract_username_tiktok, extract_content_id
from app.utils.playwright_utils import get_page, navigate_and_wait
import requests
import os
import re
import aiohttp
from TikTokApi import TikTokApi
import logging
import datetime
import json
import asyncio

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

TOKEN_FILE_PATH = os.getenv("TOKEN_FILE_PATH", "tokens.json")

def load_tokens():
    logger.debug(f"Attempting to load tokens from {TOKEN_FILE_PATH}")
    if os.path.exists(TOKEN_FILE_PATH) and os.path.getsize(TOKEN_FILE_PATH) > 0:
        try:
            with open(TOKEN_FILE_PATH, "r") as file:
                tokens = json.load(file)
                logger.debug(f"Loaded tokens: {tokens}")
                expires_at = datetime.datetime.fromtimestamp(tokens["expires_at"])
                if datetime.datetime.now() < expires_at:
                    logger.info("Valid tokens loaded \n ms_token: " + tokens["ms_token"] + "\n x_bogus: " + tokens["x_bogus"] + "\n expires_at: " + str(expires_at))
                    return tokens["ms_token"], tokens["x_bogus"], expires_at
                else:
                    logger.info("Loaded tokens are expired")
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON: {e}")
        except KeyError as e:
            logger.error(f"Missing key in tokens: {e}")
    else:
        logger.info(f"Token file not found or empty at {TOKEN_FILE_PATH}")
    return None, None, None

def save_tokens(ms_token, x_bogus, expires_at):
    logger.debug(f"Saving tokens: ms_token={ms_token}, x_bogus={x_bogus}, expires_at={expires_at}")
    tokens = {
        "ms_token": ms_token,
        "x_bogus": x_bogus,
        "expires_at": expires_at.timestamp()
    }
    with open(TOKEN_FILE_PATH, "w") as file:
        json.dump(tokens, file)
    logger.info(f"Tokens saved to {TOKEN_FILE_PATH}")

async def get_original_tiktok_link(tiktok_link):
    async with await get_page() as page:
        await navigate_and_wait(page, tiktok_link)
        return page.url

async def get_tiktok_data(tiktok_link, max_retries=3, delay=3):
    for attempt in range(max_retries):
        async with await get_page() as page:
            try:
                ms_token, x_bogus, expires_at = load_tokens()

                if ms_token and x_bogus:
                    # Tokens are still valid, return them without fetching new ones
                    final_url = await get_original_tiktok_link(tiktok_link)
                    username = extract_username_tiktok(final_url)
                    content_id = extract_content_id(final_url)
                    content_type = 'video' if '/video/' in final_url else 'photo'
                    
                    return ms_token, username, final_url, x_bogus, content_id, content_type

                await navigate_and_wait(page, tiktok_link)
                
                # Extract necessary data
                final_url = page.url
                username = extract_username_tiktok(final_url)
                content_id = extract_content_id(final_url)
                content_type = 'video' if '/video/' in final_url else 'photo'
                
                # Extract x-bogus
                x_bogus = await extract_x_bogus(page)
                
                # Extract ms_token from cookies
                cookies = await page.context.cookies()
                ms_token = next((cookie['value'] for cookie in cookies if cookie['name'] == 'msToken'), None)
                
                if not ms_token or not x_bogus:
                    raise ValueError("Failed to extract necessary tokens")
                
                return ms_token, username, final_url, x_bogus, content_id, content_type
            
            except Exception as e:
                logger.error(f"An error occurred on attempt {attempt + 1}: {str(e)}")
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(delay)
    
    raise Exception(f"Failed to extract TikTok data after {max_retries} attempts")

async def extract_x_bogus(page):
    x_bogus = None
    async def handle_request(route):
        nonlocal x_bogus
        if "x-bogus" in route.request.url.lower():
            x_bogus_match = re.search(r'X-Bogus=([^&]+)', route.request.url)
            if x_bogus_match:
                x_bogus = x_bogus_match.group(1)
        await route.continue_()
    
    await page.route("**/*", handle_request)
    await page.reload()  # Trigger a reload to capture x-bogus
    return x_bogus

async def fetch_tiktok_api_data(content_id, x_bogus):
    api_url = "https://www.tiktok.com/api/reflow/item/detail"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    params = {
        "app_id": f"{os.getenv('TIKTOK_APP_ID')}",
        "channel": f"{os.getenv('TIKTOK_CHANNEL')}",
        "item_id": content_id,
        "X-Bogus": x_bogus
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(api_url, headers=headers, params=params) as response:
            if response.status == 200:
                return await response.json()
            else:
                return None

async def get_tiktok_api_data(ms_token, username, content_url, content_id, content_type):
    async with TikTokApi() as api:
        await api.create_sessions(ms_tokens=[ms_token], num_sessions=1)
        if content_type == 'video':
            return await api.video(url=content_url).info()
        else:
            return await api.photo(url=content_url).info()

class InvalidResponseException(Exception):
    pass

async def get_tiktok_playwright(content_url, max_retries=3, delay=3):
    for attempt in range(max_retries):
        async with await get_page() as page:
            try:
                logger.info(f"Fetching content: {content_url}")
                response = await page.goto(content_url, wait_until="networkidle")

                if response.status != 200:
                    raise InvalidResponseException(f"TikTok returned an invalid response. Status code: {response.status}")

                content = await page.content()

                # Try SIGI_STATE first
                sigi_state_match = re.search(r'<script id="SIGI_STATE" type="application/json">(.*?)</script>', content, re.DOTALL)
                if sigi_state_match:
                    data = json.loads(sigi_state_match.group(1))
                    video_id = url.split('/')[-1]
                    video_info = data["ItemModule"][video_id]
                else:
                    # Try __UNIVERSAL_DATA_FOR_REHYDRATION__ next
                    universal_data_match = re.search(r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">(.*?)</script>', content, re.DOTALL)
                    if not universal_data_match:
                        raise InvalidResponseException("TikTok returned an invalid response structure.")

                    data = json.loads(universal_data_match.group(1))
                    default_scope = data.get("__DEFAULT_SCOPE__", {})
                    video_detail = default_scope.get("webapp.video-detail", {})

                    if video_detail.get("statusCode", 0) != 0:
                        raise InvalidResponseException("TikTok returned an invalid response structure.")

                    video_info = video_detail.get("itemInfo", {}).get("itemStruct")
                    if video_info is None:
                        raise InvalidResponseException("TikTok returned an invalid response structure.")

                return video_info

            except Exception as e:
                logger.error(f"An error occurred while scraping TikTok: {str(e)}")
                raise
    
    raise Exception(f"Failed to extract TikTok data after {max_retries} attempts")
