"""
Frame.io API Client for Payroll Link Lookup Bot

Fetches asset information from Frame.io API.
"""

import os
import requests
from typing import Optional
from dataclasses import dataclass
from dotenv import load_dotenv


@dataclass
class FrameIOAsset:
    name: str
    duration: str
    status: str
    url: str


def format_duration(seconds: float) -> str:
    """
    Convert seconds to human-readable duration.

    Input: 150.5
    Output: 2:30
    """
    if seconds is None or seconds == 0:
        return "0:00"

    total_seconds = int(seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60

    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes}:{secs:02d}"


def resolve_short_link(short_code: str) -> Optional[str]:
    """
    Resolve a Frame.io short link (f.io/xxx) to get the full URL.

    Returns the resolved URL or None if resolution fails.
    """
    try:
        response = requests.head(
            f"https://f.io/{short_code}",
            allow_redirects=True,
            timeout=10
        )
        return response.url
    except Exception:
        return None


def lookup_review_link(review_link_id: str, api_token: str, original_url: str) -> dict:
    """
    Look up a Frame.io review link and get the first asset's info.
    """
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.get(
            f"https://api.frame.io/v2/review_links/{review_link_id}",
            headers=headers,
            timeout=10
        )

        if response.status_code == 401:
            return {"error": "Invalid Frame.io API token", "url": original_url}

        if response.status_code == 404:
            return {"error": "Review link not found", "url": original_url}

        if response.status_code != 200:
            return {"error": f"Frame.io API error: {response.status_code}", "url": original_url}

        data = response.json()
        items = data.get("items", [])

        if not items:
            return {"error": "No assets in review link", "url": original_url}

        # Get the first asset
        asset = items[0]
        return _parse_asset(asset, original_url)

    except requests.exceptions.Timeout:
        return {"error": "Frame.io API timeout", "url": original_url}
    except requests.exceptions.RequestException as e:
        return {"error": f"Request failed: {str(e)}", "url": original_url}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}", "url": original_url}


def lookup_asset(asset_id: str, api_token: str, original_url: str) -> dict:
    """
    Look up a Frame.io asset directly.
    """
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.get(
            f"https://api.frame.io/v2/assets/{asset_id}",
            headers=headers,
            timeout=10
        )

        if response.status_code == 401:
            return {"error": "Invalid Frame.io API token", "url": original_url}

        if response.status_code == 404:
            return {"error": "Asset not found", "url": original_url}

        if response.status_code != 200:
            return {"error": f"Frame.io API error: {response.status_code}", "url": original_url}

        data = response.json()
        return _parse_asset(data, original_url)

    except requests.exceptions.Timeout:
        return {"error": "Frame.io API timeout", "url": original_url}
    except requests.exceptions.RequestException as e:
        return {"error": f"Request failed: {str(e)}", "url": original_url}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}", "url": original_url}


def _parse_asset(asset: dict, original_url: str) -> dict:
    """
    Parse asset data into response format.
    """
    name = asset.get("name", "Unknown Asset")
    duration_seconds = asset.get("duration", 0)
    duration = format_duration(duration_seconds)

    # Label can be: approved, needs_review, in_progress, or None
    label = asset.get("label", "")
    status = label.capitalize() if label else "No status"

    return {
        "name": name,
        "duration": duration,
        "status": status,
        "url": original_url
    }


def lookup_by_type(id_value: str, id_type: str, original_url: str) -> dict:
    """
    Look up Frame.io asset based on the URL type.

    Args:
        id_value: The extracted ID
        id_type: "short", "review", or "asset"
        original_url: The original URL

    Returns:
        dict with name, duration, status, url on success
        dict with error, url on failure
    """
    load_dotenv()

    api_token = os.getenv("FRAMEIO_TOKEN")
    if not api_token:
        return {"error": "FRAMEIO_TOKEN not configured", "url": original_url}

    if id_type == "short":
        # Resolve the short link first
        resolved_url = resolve_short_link(id_value)
        if not resolved_url:
            return {"error": "Could not resolve short link", "url": original_url}

        # Parse the resolved URL to determine the type
        import re

        # Check for review link
        match = re.search(r'app\.frame\.io/reviews/([a-zA-Z0-9-]+)', resolved_url)
        if match:
            return lookup_review_link(match.group(1), api_token, original_url)

        # Check for player/asset link
        match = re.search(r'app\.frame\.io/player/([a-zA-Z0-9-]+)', resolved_url)
        if match:
            return lookup_asset(match.group(1), api_token, original_url)

        # Check for presentation link (another common format)
        match = re.search(r'app\.frame\.io/presentations/([a-zA-Z0-9-]+)', resolved_url)
        if match:
            return lookup_review_link(match.group(1), api_token, original_url)

        return {"error": f"Unknown Frame.io URL format: {resolved_url}", "url": original_url}

    elif id_type == "review":
        return lookup_review_link(id_value, api_token, original_url)

    elif id_type == "asset":
        return lookup_asset(id_value, api_token, original_url)

    else:
        return {"error": f"Unknown Frame.io ID type: {id_type}", "url": original_url}


def format_response(result: dict) -> list[str]:
    """
    Format the lookup result as a list of values for Sheets.

    Returns: [name, duration, status] or [error_message]
    """
    if "error" in result:
        return [f"ERROR: {result['error']}"]

    return [result['name'], result['duration'], result['status']]


# For testing
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python lookup_frameio.py <id_type> <id>")
        print("  id_type: short, review, or asset")
        print("Example: python lookup_frameio.py short abc123")
        print("Example: python lookup_frameio.py review abc-def-123")
        sys.exit(1)

    id_type = sys.argv[1]
    id_value = sys.argv[2]

    if id_type == "short":
        url = f"https://f.io/{id_value}"
    elif id_type == "review":
        url = f"https://app.frame.io/reviews/{id_value}"
    else:
        url = f"https://app.frame.io/player/{id_value}"

    result = lookup_by_type(id_value, id_type, url)

    print("Result:")
    print(f"  {result}")
    print(f"\nFormatted: {format_response(result)}")
