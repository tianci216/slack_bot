"""
Contact Finder - BotFunction Implementation

Finds decision-maker contacts at companies for sponsorship outreach.
Two modes: industry search (browse companies) or direct lookup (company name/domain/URL).
"""

import sys
import re
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv

# Add tools directory to path for imports
TOOLS_DIR = Path(__file__).parent / "tools"
sys.path.insert(0, str(TOOLS_DIR))

# Add parent directory for core imports
PARENT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(PARENT_DIR))

from core.models import BotFunction, FunctionInfo, FunctionResponse, MessageResult
from models import Company, Contact
from google_scraper import search_companies, find_decision_maker, resolve_company_domain
from email_guesser import enrich_contact_email
import hunter_client
from sheets_client import check_duplicates, append_contacts_batch, is_configured as sheets_configured
from conversation import ConversationManager, ConversationState, SessionMode
from formatters import (
    format_company_list,
    format_contact_result,
    format_contact_not_found,
    format_batch_summary,
    format_single_lookup_result,
)

logger = logging.getLogger(__name__)

# Regex patterns for input classification
HELP_PATTERN = re.compile(r"^help$", re.IGNORECASE)
CLEAR_PATTERN = re.compile(r"^(clear|reset|start over)$", re.IGNORECASE)
SELECT_PATTERN = re.compile(r"^select\s+(.+)$", re.IGNORECASE)
MORE_PATTERN = re.compile(r"^more$", re.IGNORECASE)
SEARCH_PATTERN = re.compile(r"^search\s+(.+)$", re.IGNORECASE)
LOOKUP_PATTERN = re.compile(r"^lookup\s+(.+)$", re.IGNORECASE)
LINKEDIN_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?linkedin\.com/company/[a-zA-Z0-9_-]+/?",
    re.IGNORECASE,
)
DOMAIN_PATTERN = re.compile(
    r"^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?\.[a-zA-Z]{2,}$"
)

RESULTS_PER_PAGE = 10




class ContactFinderFunction(BotFunction):
    """
    Contact Finder function.

    Searches for decision-maker contacts at companies by industry niche
    or direct company lookup, and logs results to Google Sheets.
    """

    def __init__(self):
        env_path = Path(__file__).parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)

        self.conversation = ConversationManager()
        self._hunter_exhausted = False

        if not sheets_configured():
            logger.warning("Google Sheets not configured — results will only show in Slack")

    def get_info(self) -> FunctionInfo:
        return FunctionInfo(
            name="contact_finder",
            display_name="Contact Finder",
            slash_command="/contacts",
            description="Find decision-maker contacts at companies by industry or name",
            help_text=(
                "*Contact Finder Help*\n\n"
                "Find marketing/partnerships decision-makers at companies "
                "for sponsorship outreach.\n\n"
                "*Search modes:*\n"
                "- Type any text to browse companies (e.g., `gaming peripherals`)\n"
                "- `search <query>` - Explicitly search by industry\n"
                "- `lookup <name>` - Direct company lookup (e.g., `lookup Razer`)\n"
                "- Domains (`razer.com`) and LinkedIn URLs are always direct lookups\n\n"
                "*Commands:*\n"
                "- `select 1,3,5` - Look up contacts for selected companies\n"
                "- `select all` - Look up contacts for all listed companies\n"
                "- `more` - Next page of company results\n"
                "- `clear` - Start over\n"
                "- `help` - Show this message\n\n"
                "*Output:*\n"
                "Contact info is shown in Slack and saved to Google Sheets."
            ),
            version="1.0.0",
        )

    def handle_message(self, user_id: str, text: str, event: dict) -> FunctionResponse:
        """Route incoming messages to the appropriate handler."""
        text = text.strip()

        if HELP_PATTERN.match(text):
            return FunctionResponse(
                result=MessageResult.SUCCESS,
                messages=[self.get_info().help_text],
            )

        if CLEAR_PATTERN.match(text):
            return self._handle_clear(user_id)

        select_match = SELECT_PATTERN.match(text)
        if select_match:
            return self._handle_select(user_id, select_match.group(1))

        if MORE_PATTERN.match(text):
            return self._handle_more(user_id)

        # Explicit prefix commands
        search_match = SEARCH_PATTERN.match(text)
        if search_match:
            return self._handle_industry_search(user_id, search_match.group(1).strip())

        lookup_match = LOOKUP_PATTERN.match(text)
        if lookup_match:
            value = lookup_match.group(1).strip()
            linkedin_match = LINKEDIN_URL_PATTERN.search(value)
            if linkedin_match:
                return self._handle_direct_lookup(user_id, linkedin_url=linkedin_match.group(0).rstrip("/"))
            if DOMAIN_PATTERN.match(value.lower()):
                return self._handle_direct_lookup(user_id, domain=value.lower())
            return self._handle_direct_lookup(user_id, company_name=value)

        # Auto-classify: LinkedIn URLs and domains go to direct lookup,
        # everything else defaults to industry search
        linkedin_match = LINKEDIN_URL_PATTERN.search(text)
        if linkedin_match:
            return self._handle_direct_lookup(user_id, linkedin_url=linkedin_match.group(0).rstrip("/"))

        stripped = text.strip().lower()
        if DOMAIN_PATTERN.match(stripped):
            return self._handle_direct_lookup(user_id, domain=stripped)

        # Default: industry search (use "lookup <name>" for direct company lookup)
        return self._handle_industry_search(user_id, text.strip())

    def get_welcome_message(self) -> str:
        return (
            "You're now using *Contact Finder*.\n\n"
            "Find marketing/partnerships decision-makers at companies.\n\n"
            "Type an industry to browse companies (e.g., `gaming peripherals`), "
            "or use `lookup <name>` for a direct company lookup (e.g., `lookup Razer`).\n\n"
            "Type `help` for more info."
        )

    def on_activate(self, user_id: str) -> Optional[str]:
        state = self.conversation.get_state(user_id)
        if state and state.mode == SessionMode.AWAITING_SELECTION:
            return (
                f"Welcome back! You have search results for *{state.search_query}*.\n"
                "Use `select` to look up contacts, `more` for next page, or `clear` to start over."
            )
        return None

    def on_deactivate(self, user_id: str) -> None:
        pass

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _handle_industry_search(self, user_id: str, query: str) -> FunctionResponse:
        """Mode 1: Search for companies by industry keyword."""
        companies = search_companies(query, num_results=RESULTS_PER_PAGE)

        if isinstance(companies, dict) and "error" in companies:
            return FunctionResponse(
                result=MessageResult.ERROR,
                messages=[f"Search failed: {companies['error']}"],
                error=companies["error"],
            )

        if not companies:
            return FunctionResponse(
                result=MessageResult.NO_ACTION,
                messages=[
                    f"No companies found for *{query}*.\n"
                    "Try a broader search term."
                ],
            )

        # Save state
        state = ConversationState(
            user_id=user_id,
            mode=SessionMode.AWAITING_SELECTION,
            search_query=query,
            companies=[c.to_dict() for c in companies],
            current_page=1,
            last_updated=datetime.utcnow(),
        )
        self.conversation.set_state(state)

        msg = format_company_list(companies, query, page=1, per_page=RESULTS_PER_PAGE)
        return FunctionResponse(
            result=MessageResult.SUCCESS,
            messages=[msg],
            metadata={"company_count": len(companies), "query": query},
        )

    def _handle_more(self, user_id: str) -> FunctionResponse:
        """Fetch more company results (extends current list)."""
        state = self.conversation.get_state(user_id)
        if not state or state.mode != SessionMode.AWAITING_SELECTION:
            return FunctionResponse(
                result=MessageResult.NO_ACTION,
                messages=["No active search. Type an industry to search for companies."],
            )

        # Google doesn't paginate — fetch a larger batch
        next_page = state.current_page + 1
        more_count = RESULTS_PER_PAGE * next_page
        companies = search_companies(
            state.search_query, num_results=more_count,
        )

        if isinstance(companies, dict) and "error" in companies:
            return FunctionResponse(
                result=MessageResult.ERROR,
                messages=[f"Search failed: {companies['error']}"],
                error=companies["error"],
            )

        if not companies or len(companies) <= len(state.companies):
            return FunctionResponse(
                result=MessageResult.NO_ACTION,
                messages=["No more results. Try `select` to look up contacts or `clear` to start over."],
            )

        state.companies = [c.to_dict() for c in companies]
        state.current_page = next_page
        state.last_updated = datetime.utcnow()
        self.conversation.set_state(state)

        msg = format_company_list(
            companies, state.search_query,
            page=1, per_page=len(companies),
        )
        return FunctionResponse(
            result=MessageResult.SUCCESS,
            messages=[msg],
            metadata={"total_results": len(companies)},
        )

    def _handle_select(self, user_id: str, arg: str) -> FunctionResponse:
        """Handle company selection and batch contact lookup."""
        state = self.conversation.get_state(user_id)
        if not state or state.mode != SessionMode.AWAITING_SELECTION or not state.companies:
            return FunctionResponse(
                result=MessageResult.NO_ACTION,
                messages=["No companies to select from. Search for an industry first."],
            )

        companies = [Company.from_dict(c) for c in state.companies]
        selected: list[Company] = []

        if arg.strip().lower() == "all":
            selected = companies
        else:
            tokens = re.split(r"[,\s]+", arg.strip())
            for token in tokens:
                try:
                    idx = int(token)
                    if 1 <= idx <= len(companies):
                        selected.append(companies[idx - 1])
                except ValueError:
                    continue

        if not selected:
            return FunctionResponse(
                result=MessageResult.NO_ACTION,
                messages=[
                    "Invalid selection. Use numbers from the list "
                    "(e.g., `select 1,3,5`) or `select all`."
                ],
            )

        # Batch lookup contacts
        contacts = self._batch_lookup_contacts(selected)

        # Save to sheet and format results
        messages = self._save_and_format_batch(contacts, selected)

        # Reset to idle
        state.mode = SessionMode.IDLE
        state.contacts_found = [c.to_dict() for c in contacts if c is not None]
        state.last_updated = datetime.utcnow()
        self.conversation.set_state(state)

        return FunctionResponse(
            result=MessageResult.SUCCESS,
            messages=messages,
            metadata={"selected": len(selected), "contacts_found": len([c for c in contacts if c])},
        )

    def _handle_direct_lookup(
        self,
        user_id: str,
        company_name: Optional[str] = None,
        domain: Optional[str] = None,
        linkedin_url: Optional[str] = None,
    ) -> FunctionResponse:
        """Mode 2: Direct lookup of a single company."""
        # Build Company from what we know (no API call needed)
        name = company_name
        if linkedin_url and not name:
            # Extract company name from LinkedIn URL slug
            slug = linkedin_url.rstrip("/").split("/")[-1]
            name = slug.replace("-", " ").title()
        if not name:
            name = domain

        if not domain and name:
            domain = resolve_company_domain(name)

        company = Company(
            name=name or "Unknown",
            domain=domain,
            linkedin_url=linkedin_url,
        )

        # Look up decision maker
        contact = self._lookup_single_contact(company)

        # Save to sheet
        added = False
        already_existed = False
        sheet_error = False

        if contact and contact.email and sheets_configured():
            try:
                dupes = check_duplicates([contact.email])
                if contact.email in dupes:
                    already_existed = True
                else:
                    result = append_contacts_batch([contact.to_sheet_row()])
                    if "error" in result:
                        sheet_error = True
                    else:
                        added = True
            except Exception as e:
                logger.error(f"Sheet error for direct lookup: {e}")
                sheet_error = True

        msg = format_single_lookup_result(
            contact,
            company.name,
            added_to_sheet=added,
            already_existed=already_existed,
            sheet_error=sheet_error,
        )

        # Clear any active session
        self.conversation.clear_state(user_id)

        return FunctionResponse(
            result=MessageResult.SUCCESS,
            messages=[msg],
            metadata={"company": company.name, "contact_found": contact is not None},
        )

    def _handle_clear(self, user_id: str) -> FunctionResponse:
        """Clear the user's conversation state."""
        self.conversation.clear_state(user_id)
        return FunctionResponse(
            result=MessageResult.SUCCESS,
            messages=["Session cleared. Type an industry or company name to start a new search."],
        )

    # ------------------------------------------------------------------
    # Contact lookup logic
    # ------------------------------------------------------------------

    def _lookup_single_contact(self, company: Company) -> Optional[Contact]:
        """
        Look up a decision-maker contact at a company.

        Strategy:
        1. Try Hunter domain search first (returns contact with verified email)
        2. If Hunter quota exhausted or no result, fall back to Google scraper
        3. Guess/verify email for Google-sourced contacts
        """
        # Step 1: Try Hunter if we have a domain and quota is available
        if company.domain and not self._hunter_exhausted:
            result = hunter_client.find_best_contact(company.domain, company.name)

            if isinstance(result, dict) and "error" in result:
                error = result["error"]
                if "402" in str(error):
                    self._hunter_exhausted = True
                    logger.warning("Hunter quota exhausted — falling back to Google for remaining contacts")
                elif error != "no_contact_found":
                    logger.error(f"Hunter search error for {company.name}: {error}")
            else:
                # Hunter found a contact with a verified email
                logger.info(f"Hunter found contact for {company.name}: {result.email}")
                return result

        # Step 2: Fall back to Google people search
        contact = find_decision_maker(
            company_name=company.name,
            domain=company.domain,
        )

        if isinstance(contact, dict) and "error" in contact:
            if contact["error"] != "no_contact_found":
                logger.error(f"Google search error for {company.name}: {contact['error']}")
            return None

        # Step 3: Resolve domain if missing
        if not contact.company_domain and not company.domain:
            domain = resolve_company_domain(company.name)
            if domain:
                contact.company_domain = domain
                company.domain = domain
        elif company.domain and not contact.company_domain:
            contact.company_domain = company.domain

        # Step 4: Guess email from name + domain (no Hunter API call since quota may be gone)
        enrich_contact_email(contact)

        return contact

    def _batch_lookup_contacts(self, companies: list[Company]) -> list[Optional[Contact]]:
        """
        Look up contacts for multiple companies sequentially.

        Google blocks concurrent scraping, so lookups are serialized
        with delays handled inside google_scraper.
        """
        results = []
        for company in companies:
            try:
                contact = self._lookup_single_contact(company)
                results.append(contact)
            except Exception as e:
                logger.error(f"Error looking up contact for {company.name}: {e}")
                results.append(None)
        return results

    def _save_and_format_batch(
        self,
        contacts: list[Optional[Contact]],
        companies: list[Company],
    ) -> list[str]:
        """
        Check duplicates, save to sheet, and format batch results.

        Dedup + append is done as a single batch on the main thread
        to avoid race conditions.
        """
        found_contacts: list[Contact] = [c for c in contacts if c is not None]
        emails = [c.email for c in found_contacts if c.email]

        # Check duplicates in one batch
        existing_emails: set[str] = set()
        sheet_error = False

        if emails and sheets_configured():
            try:
                existing_emails = check_duplicates(emails)
            except Exception as e:
                logger.error(f"Duplicate check failed: {e}")
                sheet_error = True

        # Determine which rows to add
        new_rows = []
        contact_status: dict[str, str] = {}  # email -> "added" | "existed"

        for c in found_contacts:
            if c.email:
                if c.email.lower().strip() in {e.lower().strip() for e in existing_emails}:
                    contact_status[c.email] = "existed"
                else:
                    new_rows.append(c.to_sheet_row())
                    contact_status[c.email] = "added"

        # Batch append new rows
        added_count = 0
        if new_rows and sheets_configured():
            try:
                result = append_contacts_batch(new_rows)
                if "error" in result:
                    sheet_error = True
                else:
                    added_count = result.get("added", 0)
            except Exception as e:
                logger.error(f"Batch append failed: {e}")
                sheet_error = True

        # Format individual results
        messages = []
        result_lines = []
        for i, (contact, company) in enumerate(zip(contacts, companies)):
            if contact is None:
                result_lines.append(format_contact_not_found(company.name))
            else:
                was_added = contact.email and contact_status.get(contact.email) == "added"
                was_existing = contact.email and contact_status.get(contact.email) == "existed"
                result_lines.append(format_contact_result(
                    contact,
                    added_to_sheet=was_added and not sheet_error,
                    already_existed=was_existing,
                ))

        messages.append("\n\n---\n\n".join(result_lines))

        # Summary
        duplicate_count = sum(1 for s in contact_status.values() if s == "existed")
        summary = format_batch_summary(
            total=len(companies),
            found=len(found_contacts),
            added=added_count if not sheet_error else 0,
            duplicates=duplicate_count,
            sheet_errors=sheet_error,
        )
        messages.append(summary)

        return messages


def get_function() -> BotFunction:
    """Factory function called by plugin loader."""
    return ContactFinderFunction()
