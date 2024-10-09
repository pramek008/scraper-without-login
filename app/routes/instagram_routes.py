from fastapi import APIRouter, Request, HTTPException
from app.services.instagram_service import fetch_profile_data, extract_shortcode, fetch_post_data, create_compact_data, create_structured_data

router = APIRouter()

@router.get("/scrape-instagram-profile")
async def scrape_instagram_profile(request: Request):
    username = request.query_params.get("username")
    if not username:
        raise HTTPException(status_code=400, detail="Please provide a valid Instagram username.")
    profile_data = fetch_profile_data(username)
    return profile_data

@router.get("/scrape-instagram-post")
async def scrape_instagram_post(request: Request):
    url = request.query_params.get("url")
    response_type = request.query_params.get("responseType")

    if not url:
        raise HTTPException(status_code=400, detail="Please provide a valid Instagram post URL.")

    shortcode = await extract_shortcode(url)
    if not shortcode:
        raise HTTPException(status_code=400, detail="Unable to extract shortcode from URL.")

    post_data = fetch_post_data(shortcode)
    media_data = post_data.get("data", {}).get("xdt_shortcode_media", {})

    if response_type == 'compact':
        return create_compact_data(media_data, url)
    elif response_type == 'raw':
        return post_data
    elif response_type == 'all':
        return create_structured_data(media_data, url)
    else:
        return post_data
