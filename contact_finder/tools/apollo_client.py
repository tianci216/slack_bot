"""
Apollo.io API client for company search and people search.
"""

import os
import time
import logging
from typing import Optional

import requests

from models import Company, Contact

logger = logging.getLogger(__name__)

APOLLO_BASE_URL = "https://api.apollo.io"

# Titles that indicate decision-makers for sponsorship/partnerships
DECISION_MAKER_TITLES = [
    "Marketing Director",
    "VP Marketing",
    "Vice President Marketing",
    "Head of Marketing",
    "CMO",
    "Chief Marketing Officer",
    "Head of Partnerships",
    "Director of Partnerships",
    "VP Partnerships",
    "Brand Manager",
    "Head of Business Development",
    "Director of Business Development",
    "VP Business Development",
    "Director of Brand",
    "Head of Brand",
    "Director of Sponsorships",
    "Head of Sponsorships",
    "Marketing Manager",
    "Partnerships Manager",
    "Brand Partnerships",
    "Influencer Marketing Manager",
    "Director of Influencer Marketing",
]


def _get_api_key() -> Optional[str]:
    return os.getenv("APOLLO_API_KEY")


def _request_with_retry(
    method: str,
    url: str,
    max_retries: int = 3,
    **kwargs,
) -> dict:
    """Make an API request with retries and exponential backoff."""
    api_key = _get_api_key()
    if not api_key:
        return {"error": "APOLLO_API_KEY not configured"}

    headers = {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "x-api-key": api_key,
    }
    kwargs.setdefault("headers", {}).update(headers)
    kwargs.setdefault("timeout", 15)

    for attempt in range(max_retries):
        try:
            resp = requests.request(method, url, **kwargs)

            if resp.status_code == 429:
                wait = 2 ** attempt
                logger.warning(f"Apollo rate limited, waiting {wait}s (attempt {attempt + 1})")
                time.sleep(wait)
                continue

            resp.raise_for_status()
            return resp.json()

        except requests.exceptions.HTTPError as e:
            if attempt < max_retries - 1 and resp.status_code >= 500:
                time.sleep(2 ** attempt)
                continue
            logger.error(f"Apollo API error: {e}")
            return {"error": f"API error: {resp.status_code}"}

        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            logger.error(f"Apollo request failed: {e}")
            return {"error": f"Request failed: {e}"}

    return {"error": "Max retries exceeded"}


def search_companies(
    query: str,
    page: int = 1,
    per_page: int = 10,
) -> list[Company] | dict:
    """
    Search for companies by keyword.

    Args:
        query: Industry or keyword search term
        page: Page number (1-indexed)
        per_page: Results per page

    Returns:
        List of Company objects or {"error": "..."} on failure
    """
    url = f"{APOLLO_BASE_URL}/api/v1/mixed_companies/search"
    body = {
        "q": query,
        "page": page,
        "per_page": per_page,
    }

    data = _request_with_retry("POST", url, json=body)

    if "error" in data:
        return data

    companies = []
    for org in data.get("organizations", []):
        companies.append(Company(
            name=org.get("name", "Unknown"),
            domain=org.get("primary_domain"),
            linkedin_url=org.get("linkedin_url"),
            industry=org.get("industry"),
            employee_count=_format_employee_count(
                org.get("estimated_num_employees")
            ),
            apollo_id=org.get("id"),
        ))

    return companies


def find_decision_maker(
    company_name: str,
    domain: Optional[str] = None,
    apollo_id: Optional[str] = None,
) -> Contact | dict:
    """
    Search Apollo for a decision-maker at a company.

    Searches by title keywords related to marketing/partnerships.

    Args:
        company_name: Company name for the contact record
        domain: Company domain to filter by
        apollo_id: Apollo organization ID to filter by

    Returns:
        Contact object or {"error": "..."} on failure
    """
    url = f"{APOLLO_BASE_URL}/api/v1/mixed_people/api_search"

    # Apollo people search uses query params with array bracket syntax
    params = {"per_page": 5, "page": 1}

    # Add title filters as person_titles[]
    for title in DECISION_MAKER_TITLES:
        params.setdefault("person_titles[]", [])
        if isinstance(params["person_titles[]"], list):
            params["person_titles[]"].append(title)

    # Add organization filter
    if apollo_id:
        params["organization_ids[]"] = apollo_id
    elif domain:
        params["q_organization_domains_list[]"] = domain

    data = _request_with_retry("POST", url, params=params)

    if "error" in data:
        return data

    people = data.get("people", [])
    if not people:
        return {"error": "no_contact_found"}

    # Pick the best match (first result, Apollo ranks by relevance)
    person = people[0]

    email = person.get("email")
    email_status = None
    if email:
        email_status = "verified" if person.get("email_status") == "verified" else "unverified"

    return Contact(
        company_name=company_name,
        company_domain=domain,
        first_name=person.get("first_name"),
        last_name=person.get("last_name"),
        full_name=_build_full_name(person.get("first_name"), person.get("last_name")),
        title=person.get("title"),
        email=email,
        email_status=email_status,
        linkedin_url=person.get("linkedin_url"),
        phone=_extract_phone(person),
        source="apollo",
    )


def resolve_company(
    company_name: Optional[str] = None,
    domain: Optional[str] = None,
    linkedin_url: Optional[str] = None,
) -> Company | dict:
    """
    Resolve a company by name, domain, or LinkedIn URL to get its Apollo ID.

    Args:
        company_name: Company name to search for
        domain: Company domain
        linkedin_url: LinkedIn company URL

    Returns:
        Company object or {"error": "..."} on failure
    """
    url = f"{APOLLO_BASE_URL}/api/v1/mixed_companies/search"
    body = {"page": 1, "per_page": 1}

    if domain:
        body["q"] = domain
    elif linkedin_url:
        body["q"] = linkedin_url
    elif company_name:
        body["q"] = company_name
    else:
        return {"error": "No search criteria provided"}

    data = _request_with_retry("POST", url, json=body)

    if "error" in data:
        return data

    orgs = data.get("organizations", [])
    if not orgs:
        return {"error": "company_not_found"}

    org = orgs[0]
    return Company(
        name=org.get("name", "Unknown"),
        domain=org.get("primary_domain"),
        linkedin_url=org.get("linkedin_url"),
        industry=org.get("industry"),
        employee_count=_format_employee_count(
            org.get("estimated_num_employees")
        ),
        apollo_id=org.get("id"),
    )


def _build_full_name(first: Optional[str], last: Optional[str]) -> Optional[str]:
    parts = [p for p in (first, last) if p]
    return " ".join(parts) if parts else None


def _extract_phone(person: dict) -> Optional[str]:
    phones = person.get("phone_numbers", [])
    if phones:
        return phones[0].get("sanitized_number") or phones[0].get("raw_number")
    return None


def _format_employee_count(count) -> Optional[str]:
    if count is None:
        return None
    try:
        n = int(count)
        if n >= 10000:
            return f"~{n // 1000}k"
        elif n >= 1000:
            return f"~{n}"
        return str(n)
    except (ValueError, TypeError):
        return str(count)
