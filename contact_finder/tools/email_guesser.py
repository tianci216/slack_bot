"""
Email pattern guessing for finding contact emails.

Generates likely email addresses from first name, last name, and company domain.
"""

import re
import logging
from typing import Optional

from models import Contact
import hunter_client

logger = logging.getLogger(__name__)

# Set to True when Hunter returns 402 (quota exhausted) so we stop wasting API calls
_hunter_quota_exhausted = False

# Common email patterns ordered by frequency
EMAIL_PATTERNS = [
    "{first}.{last}",     # jane.smith@domain.com
    "{first}{last}",      # janesmith@domain.com
    "{fi}{last}",         # jsmith@domain.com
    "{first}",            # jane@domain.com
    "{fi}.{last}",        # j.smith@domain.com
    "{last}.{first}",     # smith.jane@domain.com
    "{first}_{last}",     # jane_smith@domain.com
    "{first}-{last}",     # jane-smith@domain.com
]


def guess_email(first_name: str, last_name: str, domain: str) -> Optional[str]:
    """
    Generate the most likely email address.

    Returns the most common pattern: first.last@domain.com
    """
    candidates = generate_candidates(first_name, last_name, domain)
    return candidates[0] if candidates else None


def generate_candidates(
    first_name: str,
    last_name: str,
    domain: str,
) -> list[str]:
    """
    Generate all email pattern candidates ordered by likelihood.

    Args:
        first_name: Contact's first name
        last_name: Contact's last name
        domain: Company domain (e.g., "razer.com")

    Returns:
        List of possible email addresses
    """
    first = _clean_name(first_name)
    last = _clean_name(last_name)

    if not first or not last or not domain:
        return []

    fi = first[0]

    candidates = []
    for pattern in EMAIL_PATTERNS:
        email_local = pattern.format(first=first, last=last, fi=fi)
        candidates.append(f"{email_local}@{domain}")

    return candidates


def enrich_contact_email(contact: Contact) -> Contact:
    """
    Add a guessed email to a Contact that has name + domain but no email.

    Modifies the contact in place and returns it.
    Sets email_status to "guessed".
    """
    if contact.email:
        return contact

    if not contact.first_name or not contact.last_name or not contact.company_domain:
        return contact

    email = guess_email(contact.first_name, contact.last_name, contact.company_domain)
    if email:
        contact.email = email
        contact.email_status = "guessed"
        if contact.source and contact.source != "google":
            contact.source = f"{contact.source}+email_guess"
        else:
            contact.source = "google+email_guess"

    return contact


def enrich_contact_email_verified(contact: Contact) -> Contact:
    """
    Add a verified email to a Contact using Hunter.io email-finder first,
    falling back to pattern guessing if Hunter can't find it or quota is exhausted.

    Modifies the contact in place and returns it.
    """
    global _hunter_quota_exhausted

    if contact.email:
        return contact

    if not contact.first_name or not contact.last_name or not contact.company_domain:
        return contact

    # Skip Hunter if quota already exhausted this session
    if _hunter_quota_exhausted:
        return enrich_contact_email(contact)

    # Try Hunter's email-finder API first
    result = hunter_client.find_email(
        domain=contact.company_domain,
        first_name=contact.first_name,
        last_name=contact.last_name,
    )

    if (
        not isinstance(result, dict)
        or "error" in result
        or not result.get("email")
    ):
        error_msg = result.get("error", "") if isinstance(result, dict) else ""

        # Detect quota exhaustion (Hunter returns HTTP 402)
        if "402" in str(error_msg):
            _hunter_quota_exhausted = True
            logger.warning("Hunter search quota exhausted — using pattern guess for remaining contacts")
        else:
            logger.info(
                f"Hunter find_email returned no result for "
                f"{contact.first_name} {contact.last_name}@{contact.company_domain}, "
                f"falling back to pattern guess"
            )

        return enrich_contact_email(contact)

    confidence = result.get("confidence") or 0
    if confidence >= 70:
        contact.email = result["email"]
        contact.email_status = "hunter_found"
        contact.source = f"{contact.source}+hunter" if contact.source else "hunter"
        logger.info(
            f"Hunter verified email {result['email']} "
            f"(confidence {confidence}) for {contact.first_name} {contact.last_name}"
        )
    else:
        # Low confidence — fall back to pattern guess
        logger.info(
            f"Hunter confidence too low ({confidence}) for "
            f"{contact.first_name} {contact.last_name}@{contact.company_domain}, "
            f"falling back to pattern guess"
        )
        return enrich_contact_email(contact)

    return contact


def _clean_name(name: str) -> str:
    """Clean a name for email generation — lowercase, alpha only."""
    if not name:
        return ""
    name = re.sub(r"[^a-zA-Z]", "", name)
    return name.lower()
