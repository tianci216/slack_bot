"""
YouTube API Client for Payroll Link Lookup Bot

Fetches video information from YouTube Data API v3.
"""

import os
import re
import requests
from typing import Optional
from dataclasses import dataclass
from dotenv import load_dotenv


@dataclass
class YouTubeVideo:
    title: str
    duration: str
    url: str


def parse_iso8601_duration(duration: str) -> str:
    """
    Parse ISO 8601 duration format to human-readable format.

    Input: PT15M33S, PT1H30M, PT45S, etc.
    Output: 15:33, 1:30:00, 0:45, etc.
    """
    # Match hours, minutes, seconds
    pattern = r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?'
    match = re.match(pattern, duration)

    if not match:
        return duration  # Return original if can't parse

    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)

    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes}:{seconds:02d}"


def lookup_video(video_id: str, original_url: str) -> dict:
    """
    Look up a YouTube video by ID.

    Args:
        video_id: The YouTube video ID (11 characters)
        original_url: The original URL for reference

    Returns:
        dict with title, duration, url on success
        dict with error, url on failure
    """
    load_dotenv()

    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        return {"error": "YOUTUBE_API_KEY not configured", "url": original_url}

    params = {
        "id": video_id,
        "part": "snippet,contentDetails",
        "key": api_key
    }

    try:
        response = requests.get(
            "https://www.googleapis.com/youtube/v3/videos",
            params=params,
            timeout=10
        )

        if response.status_code == 403:
            error_data = response.json()
            reason = error_data.get("error", {}).get("message", "API quota exceeded or invalid key")
            return {"error": f"YouTube API error: {reason}", "url": original_url}

        if response.status_code != 200:
            return {"error": f"YouTube API error: {response.status_code}", "url": original_url}

        data = response.json()
        items = data.get("items", [])

        if not items:
            return {"error": "Video not found or private", "url": original_url}

        video = items[0]
        title = video.get("snippet", {}).get("title", "Unknown Title")
        duration_iso = video.get("contentDetails", {}).get("duration", "PT0S")
        duration = parse_iso8601_duration(duration_iso)

        return {
            "title": title,
            "duration": duration,
            "url": original_url
        }

    except requests.exceptions.Timeout:
        return {"error": "YouTube API timeout", "url": original_url}
    except requests.exceptions.RequestException as e:
        return {"error": f"Request failed: {str(e)}", "url": original_url}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}", "url": original_url}


def format_response(result: dict) -> list[str]:
    """
    Format the lookup result as a list of values for Sheets.

    Returns: [title, duration] or [error_message]
    """
    if "error" in result:
        return [f"ERROR: {result['error']}"]

    return [result['title'], result['duration']]


# For testing
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python lookup_youtube.py <video_id>")
        print("Example: python lookup_youtube.py dQw4w9WgXcQ")
        sys.exit(1)

    video_id = sys.argv[1]
    result = lookup_video(video_id, f"https://www.youtube.com/watch?v={video_id}")

    print("Result:")
    print(f"  {result}")
    print(f"\nFormatted: {format_response(result)}")

    # Test duration parsing
    print("\nDuration parsing tests:")
    test_durations = ["PT15M33S", "PT1H30M", "PT45S", "PT2H5M3S", "PT0S"]
    for d in test_durations:
        print(f"  {d} -> {parse_iso8601_duration(d)}")
