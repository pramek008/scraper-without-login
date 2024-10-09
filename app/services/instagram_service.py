import requests
import json
import re
import os
import urllib.parse
import datetime
import logging
import asyncio
from app.utils.playwright_utils import get_page, navigate_and_wait
from fastapi import FastAPI, Request, HTTPException

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def fetch_profile_data(username):
    url = "https://i.instagram.com/api/v1/users/web_profile_info"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "X-IG-App-ID": f"{os.getenv('X_IG_APP_ID')}",
    }

    params = {
        "username": username
    }

    proxy = os.getenv('PROXY')
    proxies = None
    if proxy:
        proxies = {
            "http": proxy,
            "https": proxy
        }

    try:
        response = requests.get(url, headers=headers, params=params, proxies=proxies)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        raise HTTPException(status_code=400, detail=f"An error occurred: {e}")

async def extract_shortcode(url, max_retries=3, delay=5):
    shortcode = extract_shortcode_from_url(url)
    if shortcode:
        return shortcode

    for attempt in range(max_retries):
        async with await get_page() as page:
            try:
                await navigate_and_wait(page, url)
                current_url = page.url
                
                shortcode_match = re.search(r'/(?:p|reel)/([^/]+)', current_url)
                if shortcode_match:
                    return shortcode_match.group(1)
                
                content = await page.content()
                content_match = re.search(r'"shortcode":"([^"]+)"', content)
                if content_match:
                    return content_match.group(1)
                
                raise ValueError(f"Shortcode not found for URL: {url}")
            
            except Exception as e:
                logger.error(f"An error occurred on attempt {attempt + 1}: {str(e)}")
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(delay)
    
    raise Exception(f"Failed to extract shortcode after {max_retries} attempts")

def extract_shortcode_from_url(url):
    shortcode_match = re.search(r'/(?:p|reel)/([^/]+)', url)
    logger.info(f"Extracted shortcode from input URL: {shortcode_match.group(1)}")
    return shortcode_match.group(1) if shortcode_match else None

def fetch_post_data(shortcode):
    url = "https://www.instagram.com/graphql/query/"

    payload = {
        "variables": json.dumps({
            "shortcode": shortcode,
            "parent_comment_count": 24,
            "child_comment_count": 3,
            "fetch_like_count": 10,
            "has_threaded_comments": True
        }),
        "doc_id": f"{os.getenv('INSTAGRAM_DOC_ID')}",
    }

    encoded_payload = urllib.parse.urlencode(payload)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "X-IG-App-ID": f"{os.getenv('X_IG_APP_ID')}",
        "Referer": f"https://www.instagram.com/p/{shortcode}/",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    proxy = os.getenv('PROXY')
    proxies = None
    if proxy:
        proxies = {
            "http": proxy,
            "https": proxy
        }

    try:
        response = requests.post(url, data=encoded_payload, headers=headers, proxies=proxies)
        # response = requests.post(url, data=encoded_payload, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        raise HTTPException(status_code=400, detail=f"An error occurred: {e}")


def convert_timestamp_to_iso(timestamp):
    dt = datetime.datetime.utcfromtimestamp(timestamp)
    return dt.isoformat() + 'Z'

def media_kind(post_data):
    typename = post_data.get("__typename", "")
    
    if "GraphImage" in typename:
        return "image"
    elif "GraphVideo" in typename:
        return "video"
    elif "GraphSidecar" in typename:
        media_edges = post_data.get("edge_sidecar_to_children", {}).get("edges", [])
        
        if not media_edges:
            return None
        
        media_types = set()
        
        for edge in media_edges:
            media_type = edge.get("node", {}).get("__typename", "")
            if "GraphImage" in media_type:
                media_types.add("image")
            elif "GraphVideo" in media_type:
                media_types.add("video")                   
        
        if len(media_types) == 1:
            return "carouselImage" if "image" in media_types else "carouselVideo"
        else:
            return "carouselImageVideo"
    
    return None

def tagged_users(media_data):
    tagged_users = []
    for tagged_user in media_data.get("edge_media_to_tagged_user", {}).get("edges", []):
        user = tagged_user.get("node", {}).get("user", {})
        tagged_users.append({
            "original_id": user.get("id"),
            "name": user.get("full_name"),
            "username": user.get("username"),
            "profile_picture": user.get("profile_pic_url"),
            "is_verified": user.get("is_verified"),
        })
    return tagged_users

def media_kind_carousel(typename):
    if "GraphImage" in typename:
        return "image"
    elif "GraphVideo" in typename:
        return "video"
    else:
        return "unknown"

def extract_tags_from_text(text):
    # Regular expression to find all hashtags and account tags in the text
    hashtags = re.findall(r"(#\w+)", text)
    account_tags = re.findall(r"(@\w+)", text)
    return {
        "hashtags": hashtags,
        "account_tags": account_tags
    }

def media_carousel(media_data):
    media_carousel = []
    for media in media_data.get("edge_sidecar_to_children", {}).get("edges", []):
        node = media.get("node", {})
        carousel_item = {
            "original_id": node.get("id"),
            "shortcode": node.get("shortcode"),
            "display_url": node.get("display_url"),
            "is_video": node.get("is_video"),
            "media_kind": media_kind_carousel(node.get("__typename")),
            "uri": node.get("video_url") or node.get("display_url"),
            "tagged_users": tagged_users(node),
        }
        
        # Menambahkan statistik khusus untuk video
        if node.get("is_video"):
            carousel_item["statistics"] = {
                "view_count": node.get("video_view_count"),
                "play_count": node.get("video_play_count"),
            }
        
        media_carousel.append(carousel_item)
    
    return media_carousel

def comments_data(media_data):
    def child_comment_count(comment):
        child_comments = []
        for edge in comment.get("edge_threaded_comments", {}).get("edges", []):
            node = edge.get("node", {})
            child_comments.append({
                "original_id": node.get("id"),
                "timestamp": convert_timestamp_to_iso(node.get("created_at")),
                "text": node.get("text"),
                "like_count": node.get("edge_liked_by", {}).get("count", 0),
                "owner": {
                    "original_id": node.get("owner", {}).get("id"),
                    "username": node.get("owner", {}).get("username"),
                    "profile_picture": node.get("owner", {}).get("profile_pic_url"),
                }
            })
        return child_comments

    def process_comments(edges):
        comments_data = []
        for edge in edges:
            node = edge.get("node", {})
            comment = {
                "original_id": node.get("id"),
                "timestamp": convert_timestamp_to_iso(node.get("created_at")),
                "text": node.get("text"),
                "like_count": node.get("edge_liked_by", {}).get("count", 0),
                "child_comment_count": node.get("edge_threaded_comments", {}).get("count", 0),
                "owner": {
                    "original_id": node.get("owner", {}).get("id"),
                    "username": node.get("owner", {}).get("username"),
                    "profile_picture": node.get("owner", {}).get("profile_pic_url"),
                },
                "child_comments": child_comment_count(node),
            }
            comments_data.append(comment)
        return comments_data

    # Check if media_data is a list (edges) or a dictionary
    if isinstance(media_data, list):
        return process_comments(media_data)
    else:
        parent_comments = media_data.get("edge_media_to_parent_comment", {}).get("edges", [])
        preview_comments = media_data.get("edge_media_preview_comment", {}).get("edges", [])

        if parent_comments:
            return process_comments(parent_comments)
        elif preview_comments:
            return process_comments(preview_comments)
        else:
            return []


def location_data(location):
    data = location.get("location", {})
    return {
        "original_id": data.get("id"),
        "has_public_page": data.get("has_public_page"),
        "name": data.get("name"),
        "slug": data.get("slug"),
        "address_json": data.get("address_json"),
    }

def audio_info(media_data):
    audio_data = media_data.get("clips_music_attribution_info", {})
    return {
        "artist_name": audio_data.get("artist_name"),
        "song_name": audio_data.get("song_name"),
        "uses_original_audio": audio_data.get("uses_original_audio"),
        "audio_id": audio_data.get("audio_id"),
    }

def create_compact_data(media_data, url):
    like_count = media_data.get("edge_media_preview_like", {}).get("count", 0)
    comment_count = media_data.get("edge_media_to_parent_comment", {}).get("count", 0)
    share_count = 0
    play_count = media_data.get("video_play_count", 0)
    views_count = media_data.get("video_view_count", 0)

    return {   
        "post": {
            "original_id": media_data.get("id"),
            "timestamp": convert_timestamp_to_iso(media_data.get("taken_at_timestamp")),
            "uri": url,
            "statistics": {
                "like_count": like_count,
                "comment_count": comment_count,
                "share_count": share_count,
                "play_count": play_count,
                "views_count": views_count,
            },
            "text": media_data.get("edge_media_to_caption", {}).get("edges", [{}])[0].get("node", {}).get("text"),
            "media_kind": media_kind(media_data),
        },
        "user": {
            "original_id": media_data.get("owner", {}).get("id"),
            "name": media_data.get("owner", {}).get("full_name"),
            "username": media_data.get("owner", {}).get("username"),
            "statistics": {
                "follower_count": media_data.get("owner", {}).get("edge_followed_by", {}).get("count"),
            }
        },
        "created_at": datetime.datetime.now().isoformat(),
        "updated_at": datetime.datetime.now().isoformat(),
        "engagement_count": like_count + comment_count + share_count + play_count + views_count
    }

def create_structured_data(media_data, url):
    caption_text = media_data.get("edge_media_to_caption", {}).get("edges", [{}])[0].get("node", {}).get("text", "")
    tags_data = extract_tags_from_text(caption_text)
    
    post_data ={   
        "post": {
            "original_id": media_data.get("id"),
            "uri": url,
            "shortcode": media_data.get("shortcode"),
            "timestamp": convert_timestamp_to_iso(media_data.get("taken_at_timestamp")),
            "display_url": media_data.get("display_url"),
            "media_kind": media_kind(media_data),
            "is_video": media_data.get("is_video"),
            "text": media_data.get("edge_media_to_caption", {}).get("edges", [{}])[0].get("node", {}).get("text"),
            "tags": tags_data,
            "statistics": {
                "like_count": media_data.get("edge_media_preview_like", {}).get("count", 0),
                "comment_count": media_data.get("edge_media_to_parent_comment", {}).get("count", 0),
                "share_count": media_data.get("edge_media_to_share", {}).get("count", 0),
                "play_count": media_data.get("video_play_count", 0),
                "views_count": media_data.get("video_view_count", 0),
            },
            "media_carousel": media_carousel(media_data),
            "tagged_users": tagged_users(media_data),
            "comments": comments_data(media_data.get("edge_media_to_parent_comment", {}).get("edges", [])),
            },
        "owner": {
            "original_id": media_data.get("owner", {}).get("id"),
            "name": media_data.get("owner", {}).get("full_name"),
            "username": media_data.get("owner", {}).get("username"),
            "profile_picture": media_data.get("owner", {}).get("profile_pic_url"),
            "is_verified": media_data.get("owner", {}).get("is_verified"),
            "is_private": media_data.get("owner", {}).get("is_private"),
            "statistics": {
                "follower_count": media_data.get("owner", {}).get("edge_followed_by", {}).get("count"),
                "media_count": media_data.get("owner", {}).get("edge_owner_to_timeline_media", {}).get("count"),
            }
        },
        "updated_at": datetime.datetime.now().isoformat(),
    }
    
    if media_data.get("location"):
        post_data["post"]["location"] =  location_data(media_data)

    if media_data.get("has_audio"):
        post_data["post"]["audio_info"] =  audio_info(media_data)

    if media_data.get("is_video"):
        post_data["post"]["statistics"]["video_duration"] =  media_data.get("video_duration")

    return post_data

