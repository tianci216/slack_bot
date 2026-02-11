"""
Hunter.io API client for email finding as a fallback.
"""

import os
import time
import logging
from typing import Optional

import requests

from models import Contact

logger = logging.getLogger(__name__)

HUNTER_BASE_URL = "https://api.hunter.io"


def _get_api_key() -> Optional[str]:
    return os.getenv("HUNTER_API_KEY")


def _request_with_retry(
    url: str,
    params: dict,
    max_retries: int = 3,
) -> dict:
    """Make a GET request with retries and exponential backoff."""
    api_key = _get_api_key()
    if not api_key:
        return {"error": "HUNTER_API_KEY not configured"}

    params["api_key"] = api_key

    for attempt in range(max_retries):
        try:
            resp = requests.get(url, params=params, timeout=15)

            if resp.status_code == 429:
                wait = 2 ** attempt
                logger.warning(f"Hunter rate limited, waiting {wait}s (attempt {attempt + 1})")
                time.sleep(wait)
                continue

            resp.raise_for_status()
            return resp.json()

        except requests.exceptions.HTTPError as e:
            if attempt < max_retries - 1 and resp.status_code >= 500:
                time.sleep(2 ** attempt)
                continue
            logger.error(f"Hunter API error: {e}")
            return {"error": f"API error: {resp.status_code}"}

        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            logger.error(f"Hunter request failed: {e}")
            return {"error": f"Request failed: {e}"}

    return {"error": "Max retries exceeded"}


def domain_search(domain: str) -> list[dict] | dict:
    """
    Search for emails at a domain, filtering for marketing/partnerships roles.

    Args:
        domain: Company domain (e.g., "razer.com")

    Returns:
        List of email dicts or {"error": "..."} on failure
    """
    url = f"{HUNTER_BASE_URL}/v2/domain-search"
    params = {
        "domain": domain,
        "type": "personal",
        "limit": 10,
    }

    data = _request_with_retry(url, params)

    if "error" in data:
        return data

    emails = data.get("data", {}).get("emails", [])
    return emails


def find_email(
    domain: str,
    first_name: str,
    last_name: str,
) -> dict:
    """
    Find a specific person's email at a domain.

    Args:
        domain: Company domain
        first_name: Person's first name
        last_name: Person's last name

    Returns:
        Dict with email and confidence, or {"error": "..."}
    """
    url = f"{HUNTER_BASE_URL}/v2/email-finder"
    params = {
        "domain": domain,
        "first_name": first_name,
        "last_name": last_name,
    }

    data = _request_with_retry(url, params)

    if "error" in data:
        return data

    result = data.get("data", {})
    return {
        "email": result.get("email"),
        "confidence": result.get("score"),
        "status": result.get("status"),
    }


def find_best_contact(domain: str, company_name: str) -> Contact | dict:
    """
    Search Hunter for the best marketing/partnerships contact at a domain.

    Used as fallback when Apollo has no person results.

    Args:
        domain: Company domain
        company_name: Company name for the contact record

    Returns:
        Contact object or {"error": "..."} on failure
    """
    # Title keywords that indicate decision-makers
    target_keywords = {
        "marketing", "partnerships", "sponsorship", "brand",
        "business development", "influencer", "cmo",
    }

    emails = domain_search(domain)
    if isinstance(emails, dict) and "error" in emails:
        return emails

    if not emails:
        return {"error": "no_contact_found"}

    # Score each email by how well the position matches
    best = None
    best_score = -1

    for entry in emails:
        position = (entry.get("position") or "").lower()
        score = sum(1 for kw in target_keywords if kw in position)

        # Prefer higher confidence emails
        confidence = entry.get("confidence", 0) or 0
        score += confidence / 200  # Small bonus for confidence

        if score > best_score:
            best_score = score
            best = entry

    if not best:
        return {"error": "no_contact_found"}

    first_name = best.get("first_name")
    last_name = best.get("last_name")
    full_name = None
    if first_name or last_name:
        parts = [p for p in (first_name, last_name) if p]
        full_name = " ".join(parts)

    return Contact(
        company_name=company_name,
        company_domain=domain,
        first_name=first_name,
        last_name=last_name,
        full_name=full_name,
        title=best.get("position"),
        email=best.get("value"),
        email_status="hunter_found",
        linkedin_url=best.get("linkedin"),
        phone=best.get("phone_number"),
        source="hunter",
    )
