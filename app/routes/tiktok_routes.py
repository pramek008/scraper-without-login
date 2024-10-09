import logging
from fastapi import APIRouter, Request, HTTPException
from app.services.tiktok_service import get_tiktok_data, fetch_tiktok_api_data, get_tiktok_api_data, get_tiktok_playwright

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/scrape-tiktok")
async def scrape_tiktok(request: Request):
    url = request.query_params.get("url")
    if not url:
        raise HTTPException(status_code=400, detail="Please provide a valid TikTok URL.")

    try:
        ms_token, username, final_url, x_bogus, content_id, content_type = await get_tiktok_data(url)

        if all([ms_token, username, x_bogus, content_id]):
            if content_type == 'photo':
                logger.info(f"Fetching TikTok photo data for {username}...")
                tiktok_data = await fetch_tiktok_api_data(content_id, x_bogus)
            else:
                logger.info(f"Fetching TikTok video data for {username}...")
                tiktok_data = await get_tiktok_playwright(final_url)
                # tiktok_data = await get_tiktok_api_data(ms_token, username, final_url, content_id, content_type)

            if tiktok_data:
                return tiktok_data
            else:
                raise HTTPException(status_code=400, detail="Failed to fetch TikTok data.")
        else:
            raise HTTPException(status_code=400, detail="Failed to retrieve all necessary data for TikTok scraping.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")
