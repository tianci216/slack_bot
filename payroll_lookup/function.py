"""
Payroll Link Lookup - BotFunction Implementation

Wraps the existing link lookup functionality in the BotFunction interface.
"""

import sys
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

# Add tools directory to path for imports
TOOLS_DIR = Path(__file__).parent / "tools"
sys.path.insert(0, str(TOOLS_DIR))

# Add parent directory for core imports
PARENT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(PARENT_DIR))

from core.models import BotFunction, FunctionInfo, FunctionResponse, MessageResult
from url_parser import parse_url, extract_urls, ParsedURL
from lookup_clickup import lookup_task, format_response as format_clickup
from lookup_youtube import lookup_video, format_response as format_youtube
from lookup_frameio import lookup_by_type, format_response as format_frameio

logger = logging.getLogger(__name__)


class PayrollLookupFunction(BotFunction):
    """Link lookup function for ClickUp, YouTube, and Frame.io URLs."""

    def __init__(self):
        # Load function-specific environment
        env_path = Path(__file__).parent / ".env"
        load_dotenv(env_path)

    def get_info(self) -> FunctionInfo:
        return FunctionInfo(
            name="payroll_lookup",
            display_name="Payroll Link Lookup",
            slash_command="/payroll",
            description="Look up ClickUp, YouTube, and Frame.io links",
            help_text=(
                "*Payroll Link Lookup Help*\n\n"
                "Paste one or more links and I'll look them up.\n\n"
                "*Supported services:*\n"
                "- ClickUp tasks\n"
                "- YouTube videos\n"
                "- Frame.io review links\n\n"
                "*Output:* Values organized by column for easy paste to Google Sheets"
            ),
            version="1.0.0"
        )

    def handle_message(self, user_id: str, text: str, event: dict) -> FunctionResponse:
        """Process links and return lookup results."""

        # Handle help command
        if text.strip().lower() == "help":
            return FunctionResponse(
                result=MessageResult.SUCCESS,
                messages=[self.get_info().help_text]
            )

        # Extract URLs
        urls = extract_urls(text)

        if not urls:
            return FunctionResponse(
                result=MessageResult.NO_ACTION,
                messages=[
                    "No URLs detected. Paste ClickUp, YouTube, or Frame.io "
                    "links and I'll look them up."
                ]
            )

        logger.info(f"Processing {len(urls)} URLs for user {user_id}")

        # Process URLs
        responses = self._process_links(urls)

        # Format output as column-grouped messages
        messages = self._format_for_sheets(responses)

        return FunctionResponse(
            result=MessageResult.SUCCESS,
            messages=messages,
            metadata={"url_count": len(urls)}
        )

    def get_welcome_message(self) -> str:
        return (
            "You're now using *Payroll Link Lookup*.\n\n"
            "Paste ClickUp, YouTube, or Frame.io links and I'll return "
            "the data formatted for Google Sheets.\n\n"
            "Type `help` for more info."
        )

    def _lookup_single_url(self, parsed: ParsedURL) -> tuple[ParsedURL, list[str]]:
        """Perform lookup for a single parsed URL."""
        try:
            if parsed.service == "clickup":
                result = lookup_task(parsed.id, parsed.url)
                return (parsed, format_clickup(result))

            elif parsed.service == "youtube":
                result = lookup_video(parsed.id, parsed.url)
                return (parsed, format_youtube(result))

            elif parsed.service == "frameio":
                result = lookup_by_type(parsed.id, parsed.id_type, parsed.url)
                return (parsed, format_frameio(result))

            else:
                return (parsed, [f"ERROR: Unknown service: {parsed.service}"])

        except Exception as e:
            logger.exception(f"Error looking up {parsed.url}")
            return (parsed, [f"ERROR: {str(e)}"])

    def _process_links(self, urls: list[str]) -> list[list[str]]:
        """Process multiple URLs in parallel."""
        url_to_parsed = {}
        parsed_list = []

        for url in urls:
            parsed = parse_url(url)
            if parsed:
                url_to_parsed[url] = parsed
                parsed_list.append(parsed)
            else:
                url_to_parsed[url] = None

        results = {}

        if parsed_list:
            with ThreadPoolExecutor(max_workers=5) as executor:
                future_to_parsed = {
                    executor.submit(self._lookup_single_url, p): p
                    for p in parsed_list
                }

                for future in as_completed(future_to_parsed):
                    parsed, response = future.result()
                    results[parsed.url] = response

        # Build response in original order
        responses = []
        for url in urls:
            if url_to_parsed[url] is None:
                responses.append(["ERROR: Unrecognized URL format"])
            else:
                responses.append(results.get(url, ["ERROR: Lookup failed"]))

        return responses

    def _format_for_sheets(self, responses: list[list[str]]) -> list[str]:
        """Group values by column for easy paste to Sheets."""
        if not responses:
            return []

        max_cols = max(len(values) for values in responses)
        messages = []

        for col_idx in range(max_cols):
            column_values = []
            for url_values in responses:
                if col_idx < len(url_values):
                    column_values.append(url_values[col_idx])
                else:
                    column_values.append("")
            messages.append("\n".join(column_values))

        return messages


def get_function() -> BotFunction:
    """Factory function called by plugin loader."""
    return PayrollLookupFunction()
