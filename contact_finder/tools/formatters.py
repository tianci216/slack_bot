"""
Slack message formatting for Contact Finder.
"""

from models import Company, Contact


def format_company_list(
    companies: list[Company],
    query: str,
    page: int = 1,
    per_page: int = 10,
) -> str:
    """
    Format a numbered list of companies for Slack.

    Args:
        companies: List of Company objects
        query: Original search query
        page: Current page number
        per_page: Results per page
    """
    if not companies:
        return (
            f"No companies found for *{query}*.\n\n"
            "Try a broader search term or check the spelling."
        )

    lines = [f"*Companies found for \"{query}\":*\n"]

    for i, c in enumerate(companies, start=1):
        parts = [f"{i}. *{c.name}*"]
        if c.domain:
            parts.append(f"{c.domain}")
        if c.industry:
            parts.append(f"{c.industry}")
        if c.employee_count:
            parts.append(f"{c.employee_count} employees")
        lines.append(" | ".join(parts))

    lines.append("")
    lines.append("*Commands:*")
    lines.append("`select 1,3,5` - Look up contacts for specific companies")
    lines.append("`select all` - Look up contacts for all listed companies")
    if len(companies) >= per_page:
        lines.append("`more` - Next page of results")
    lines.append("`clear` - Start over")

    return "\n".join(lines)


def format_contact_result(
    contact: Contact,
    added_to_sheet: bool = False,
    already_existed: bool = False,
) -> str:
    """
    Format a single contact result for Slack.

    Args:
        contact: Contact object
        added_to_sheet: Whether the contact was added to the sheet
        already_existed: Whether the contact already existed in the sheet
    """
    sheet_note = ""
    if added_to_sheet:
        sheet_note = " _(added to sheet)_"
    elif already_existed:
        sheet_note = " _(already in sheet)_"

    lines = [f"*{contact.company_name}*{sheet_note}"]

    if contact.full_name:
        lines.append(f"  Contact: {contact.full_name}")
    if contact.title:
        lines.append(f"  Title: {contact.title}")
    if contact.email:
        status = f" ({contact.email_status})" if contact.email_status else ""
        lines.append(f"  Email: {contact.email}{status}")
    if contact.linkedin_url:
        lines.append(f"  LinkedIn: {contact.linkedin_url}")
    if contact.phone:
        lines.append(f"  Phone: {contact.phone}")

    if not contact.full_name and not contact.email:
        lines.append("  _No contact found at this company_")

    return "\n".join(lines)


def format_contact_not_found(company_name: str) -> str:
    """Format a message when no contact was found."""
    return f"*{company_name}*\n  _No decision-maker contact found_"


def format_batch_summary(
    total: int,
    found: int,
    added: int,
    duplicates: int,
    sheet_errors: bool = False,
) -> str:
    """
    Format a summary after batch contact lookup.

    Args:
        total: Total companies looked up
        found: Contacts found
        added: Contacts added to sheet
        duplicates: Contacts that already existed in sheet
        sheet_errors: Whether there were sheet write errors
    """
    parts = [f"{found} contact{'s' if found != 1 else ''} found"]

    if added > 0:
        parts.append(f"{added} added to sheet")
    if duplicates > 0:
        parts.append(f"{duplicates} already in sheet")
    if sheet_errors:
        parts.append("could not save to sheet")

    return f"_Summary: {', '.join(parts)}_"


def format_single_lookup_result(
    contact: Contact | None,
    company_name: str,
    added_to_sheet: bool = False,
    already_existed: bool = False,
    sheet_error: bool = False,
) -> str:
    """Format the result of a single direct lookup."""
    if contact is None:
        return format_contact_not_found(company_name)

    result = format_contact_result(
        contact,
        added_to_sheet=added_to_sheet,
        already_existed=already_existed,
    )

    if sheet_error:
        result += "\n_Could not save to sheet_"

    return result
