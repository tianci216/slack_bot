"""
Google Custom Search API for company search and people search.

Uses Google Programmable Search Engine (CSE) to find LinkedIn company pages
and decision-maker profiles. Requires GOOGLE_CSE_API_KEY and GOOGLE_CSE_CX
environment variables.

Free tier: 100 searches/day.
"""

import os
import re
import logging
from typing import Optional
from urllib.parse import urlparse

import requests

from models import Company, Contact

logger = logging.getLogger(__name__)

CSE_ENDPOINT = "https://www.googleapis.com/customsearch/v1"

# Decision-maker titles for search queries (subset for query length)
TITLE_KEYWORDS = [
    "Marketing Director",
    "VP Marketing",
    "CMO",
    "Head of Partnerships",
    "Director of Partnerships",
    "Head of Business Development",
]

# Extended list for matching against result titles
TITLE_MATCH_KEYWORDS = [
    "marketing", "partnerships", "brand", "sponsorship",
    "business development", "cmo", "chief marketing",
    "influencer", "growth",
]

# Domains to skip when resolving company websites
SKIP_DOMAINS = {
    "linkedin.com", "facebook.com", "twitter.com", "x.com",
    "instagram.com", "youtube.com", "wikipedia.org", "wikimedia.org",
    "glassdoor.com", "indeed.com", "crunchbase.com", "bloomberg.com",
    "reddit.com", "medium.com", "tiktok.com", "pinterest.com",
    "yelp.com", "bbb.org", "google.com", "apple.com",
    "amazon.com", "github.com",
}


def _get_cse_credentials() -> tuple[Optional[str], Optional[str]]:
    """Get Google CSE API key and search engine ID."""
    return os.getenv("GOOGLE_CSE_API_KEY"), os.getenv("GOOGLE_CSE_CX")


def _cse_search(query: str, num: int = 10, start: int = 1) -> list[dict] | dict:
    """
    Execute a Google Custom Search API query.

    Args:
        query: Search query string
        num: Number of results (1-10 per request)
        start: Starting index (1-based)

    Returns:
        List of result dicts with 'title', 'link', 'snippet' keys,
        or {"error": "..."} on failure.
    """
    api_key, cx = _get_cse_credentials()
    if not api_key or not cx:
        return {"error": "GOOGLE_CSE_API_KEY or GOOGLE_CSE_CX not configured"}

    params = {
        "key": api_key,
        "cx": cx,
        "q": query,
        "num": min(num, 10),
        "start": start,
    }

    try:
        resp = requests.get(CSE_ENDPOINT, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        items = data.get("items", [])
        return [
            {
                "title": item.get("title", ""),
                "link": item.get("link", ""),
                "snippet": item.get("snippet", ""),
            }
            for item in items
        ]

    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else "unknown"
        if status == 429:
            return {"error": "Google CSE daily quota exceeded (100/day). Try again tomorrow."}
        logger.error(f"Google CSE HTTP error: {e}")
        return {"error": f"Search API error: {status}"}

    except requests.exceptions.RequestException as e:
        logger.error(f"Google CSE request failed: {e}")
        return {"error": f"Search request failed: {e}"}


def search_companies(query: str, num_results: int = 10) -> list[Company] | dict:
    """
    Search for companies by industry using Google CSE.

    Uses: site:linkedin.com/company "query"

    Args:
        query: Industry or keyword search term
        num_results: Number of results to fetch

    Returns:
        List of Company objects or {"error": "..."} on failure
    """
    search_query = f'site:linkedin.com/company "{query}"'

    results = _cse_search(search_query, num=num_results)
    if isinstance(results, dict) and "error" in results:
        return results

    companies = []
    seen_names = set()

    for result in results:
        company = _parse_linkedin_company(
            result["link"], result["title"], result["snippet"],
        )
        if company and company.name.lower() not in seen_names:
            seen_names.add(company.name.lower())
            companies.append(company)

    return companies


def find_decision_maker(
    company_name: str,
    domain: Optional[str] = None,
) -> Contact | dict:
    """
    Find a decision maker at a company using Google CSE.

    Uses: site:linkedin.com/in ("Title1" OR "Title2") "company_name"

    Args:
        company_name: Company name to search for
        domain: Company domain (used for contact record, not for query)

    Returns:
        Contact object or {"error": "..."} on failure
    """
    title_query = " OR ".join(f'"{t}"' for t in TITLE_KEYWORDS)
    search_query = f'site:linkedin.com/in ({title_query}) "{company_name}"'

    results = _cse_search(search_query, num=5)
    if isinstance(results, dict) and "error" in results:
        return results

    for result in results:
        contact = _parse_linkedin_person(
            result["link"], result["title"], result["snippet"],
            company_name=company_name, domain=domain,
        )
        if contact:
            return contact

    return {"error": "no_contact_found"}


def resolve_company_domain(company_name: str) -> Optional[str]:
    """
    Try to find a company's domain using Google CSE.

    Uses: "company_name" official website

    Args:
        company_name: Company name to look up

    Returns:
        Domain string (e.g., "razer.com") or None
    """
    search_query = f'"{company_name}" official website'

    results = _cse_search(search_query, num=5)
    if isinstance(results, dict) and "error" in results:
        return None

    for result in results:
        domain = _extract_domain(result["link"])
        if domain and not _is_skip_domain(domain):
            return domain

    return None


# ------------------------------------------------------------------
# Parsers
# ------------------------------------------------------------------

def _parse_linkedin_company(
    url: str, title: str, description: str,
) -> Optional[Company]:
    """
    Parse a LinkedIn company search result into a Company object.

    Expected title formats:
    - "Razer Inc | LinkedIn"
    - "Razer Inc - Overview | LinkedIn"
    - "Razer Inc: Overview | LinkedIn"
    """
    if "/company/" not in url.lower():
        return None

    # Remove "| LinkedIn" or " - LinkedIn" suffix
    name = title.split("|")[0].strip()
    name = re.sub(r"\s*-\s*LinkedIn\s*$", "", name, flags=re.IGNORECASE).strip()

    # Remove common suffixes like "- Overview", ": Overview"
    name = re.split(
        r"\s*[-:]\s*(?:Overview|About|Jobs|People)",
        name, flags=re.IGNORECASE,
    )[0].strip()

    if not name or name.lower() == "linkedin":
        return None

    linkedin_url = url.rstrip("/")

    return Company(
        name=name,
        linkedin_url=linkedin_url,
    )


def _parse_linkedin_person(
    url: str, title: str, description: str,
    company_name: str, domain: Optional[str] = None,
) -> Optional[Contact]:
    """
    Parse a LinkedIn person search result into a Contact object.

    Expected title formats:
    - "Jane Smith - Marketing Director - Razer | LinkedIn"
    - "Jane Smith - Marketing Director at Razer | LinkedIn"
    - "Jane Smith | LinkedIn" (less useful but parseable)
    """
    if "/in/" not in url.lower():
        return None

    # Remove "| LinkedIn" suffix
    cleaned = title.split("|")[0].strip()
    if not cleaned:
        return None

    # Try splitting by " - "
    segments = [s.strip() for s in cleaned.split(" - ")]

    full_name = None
    person_title = None

    if len(segments) >= 2:
        full_name = segments[0]
        title_part = segments[1]

        # Handle "Title at Company" format within segment
        at_split = title_part.split(" at ")
        if len(at_split) > 1:
            person_title = at_split[0].strip()
        else:
            person_title = title_part
    elif len(segments) == 1:
        # Try "Name at Company" format
        at_split = cleaned.split(" at ")
        if len(at_split) > 1:
            full_name = at_split[0].strip()
        else:
            full_name = segments[0]

    if not full_name:
        return None

    # Validate: check if the title is relevant to marketing/partnerships
    if person_title:
        title_lower = person_title.lower()
        is_relevant = any(kw in title_lower for kw in TITLE_MATCH_KEYWORDS)
        if not is_relevant:
            return None

    # Split full name into first/last
    name_parts = full_name.split()
    first_name = name_parts[0] if name_parts else None
    last_name = name_parts[-1] if len(name_parts) > 1 else None

    return Contact(
        company_name=company_name,
        company_domain=domain,
        first_name=first_name,
        last_name=last_name,
        full_name=full_name,
        title=person_title,
        linkedin_url=url.rstrip("/"),
        source="google",
    )


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _extract_domain(url: str) -> Optional[str]:
    """Extract the domain from a URL, stripping www. prefix."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        return domain if domain else None
    except Exception:
        return None


def _is_skip_domain(domain: str) -> bool:
    """Check if a domain should be skipped (social media, etc.)."""
    return any(domain == skip or domain.endswith(f".{skip}") for skip in SKIP_DOMAINS)
