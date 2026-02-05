"""
URL Parser for Payroll Link Lookup Bot

Parses URLs and extracts service-specific IDs for ClickUp, YouTube, and Frame.io links.
"""

import re
from typing import Optional
from dataclasses import dataclass


@dataclass
class ParsedURL:
    service: str  # "clickup", "youtube", "frameio"
    id: str       # The extracted ID
    url: str      # Original URL
    id_type: Optional[str] = None  # For Frame.io: "short", "review", "asset"


def parse_url(url: str) -> Optional[ParsedURL]:
    """
    Parse a URL and extract service-specific ID.

    Returns ParsedURL if recognized, None otherwise.
    """
    url = url.strip()

    # Try each parser in order
    result = (
        _parse_clickup(url) or
        _parse_youtube(url) or
        _parse_frameio(url)
    )

    return result


def _parse_clickup(url: str) -> Optional[ParsedURL]:
    """
    Parse ClickUp URLs.

    Formats:
    - https://app.clickup.com/t/{task_id}
    - https://app.clickup.com/{team_id}/v/li/{list_id}?task={task_id}
    """
    # Direct task URL: /t/{task_id}
    match = re.search(r'app\.clickup\.com/t/([a-zA-Z0-9]+)', url)
    if match:
        return ParsedURL(service="clickup", id=match.group(1), url=url)

    # Task in list view: ?task={task_id}
    match = re.search(r'app\.clickup\.com/.*[?&]task=([a-zA-Z0-9]+)', url)
    if match:
        return ParsedURL(service="clickup", id=match.group(1), url=url)

    return None


def _parse_youtube(url: str) -> Optional[ParsedURL]:
    """
    Parse YouTube URLs.

    Formats:
    - https://www.youtube.com/watch?v={video_id}
    - https://youtu.be/{video_id}
    - https://youtube.com/watch?v={video_id}&...
    """
    # youtu.be short links
    match = re.search(r'youtu\.be/([a-zA-Z0-9_-]{11})', url)
    if match:
        return ParsedURL(service="youtube", id=match.group(1), url=url)

    # youtube.com/watch?v=
    match = re.search(r'youtube\.com/watch\?.*v=([a-zA-Z0-9_-]{11})', url)
    if match:
        return ParsedURL(service="youtube", id=match.group(1), url=url)

    return None


def _parse_frameio(url: str) -> Optional[ParsedURL]:
    """
    Parse Frame.io URLs.

    Formats:
    - https://f.io/{short_code} (short share links)
    - https://app.frame.io/reviews/{review_link_id}
    - https://app.frame.io/player/{asset_id}
    """
    # Short links: f.io/{code}
    match = re.search(r'f\.io/([a-zA-Z0-9]+)', url)
    if match:
        return ParsedURL(service="frameio", id=match.group(1), url=url, id_type="short")

    # Review links: /reviews/{id}
    match = re.search(r'app\.frame\.io/reviews/([a-zA-Z0-9-]+)', url)
    if match:
        return ParsedURL(service="frameio", id=match.group(1), url=url, id_type="review")

    # Player/asset links: /player/{id}
    match = re.search(r'app\.frame\.io/player/([a-zA-Z0-9-]+)', url)
    if match:
        return ParsedURL(service="frameio", id=match.group(1), url=url, id_type="asset")

    return None


def extract_urls(text: str) -> list[str]:
    """
    Extract all URLs from a text message.

    Returns list of URL strings found in the text.
    """
    # Match URLs starting with http:// or https://
    url_pattern = r'https?://[^\s<>\[\]()]+[^\s<>\[\]().,;:!?\'")\]]'
    urls = re.findall(url_pattern, text)
    return urls


def parse_all_urls(text: str) -> list[ParsedURL]:
    """
    Extract and parse all recognized URLs from text.

    Returns list of ParsedURL objects for recognized services.
    Unrecognized URLs are skipped.
    """
    urls = extract_urls(text)
    parsed = []

    for url in urls:
        result = parse_url(url)
        if result:
            parsed.append(result)

    return parsed


# For testing
if __name__ == "__main__":
    test_urls = [
        "https://app.clickup.com/t/86a1b2c3d",
        "https://app.clickup.com/12345/v/li/67890?task=abc123",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ",
        "https://youtube.com/watch?v=dQw4w9WgXcQ&list=PLtest",
        "https://f.io/abc123",
        "https://app.frame.io/reviews/abc-def-123",
        "https://app.frame.io/player/xyz-789",
    ]

    print("Testing URL parser:\n")
    for url in test_urls:
        result = parse_url(url)
        if result:
            print(f"  {result.service}: {result.id} (type: {result.id_type})")
            print(f"    URL: {url}\n")
        else:
            print(f"  UNRECOGNIZED: {url}\n")

    # Test extract_urls
    test_text = """
    Check these links:
    https://app.clickup.com/t/task1
    https://youtu.be/video123
    Also this one: https://f.io/share1
    """

    print("\nTesting extract_urls:")
    print(f"  Found: {extract_urls(test_text)}")
