"""
Slack Bot for Payroll Link Lookup

Main bot handler that listens for DMs and performs bulk link lookups.
Uses Socket Mode for VPS deployment without public URL.
"""

import os
import sys
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

# Import our lookup tools
from url_parser import parse_url, extract_urls, ParsedURL
from lookup_clickup import lookup_task, format_response as format_clickup
from lookup_youtube import lookup_video, format_response as format_youtube
from lookup_frameio import lookup_by_type, format_response as format_frameio

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_environment():
    """Load and validate environment variables."""
    load_dotenv()

    required_vars = ["SLACK_BOT_TOKEN", "SLACK_APP_TOKEN"]
    missing = [var for var in required_vars if not os.getenv(var)]

    if missing:
        logger.error(f"Missing required environment variables: {', '.join(missing)}")
        sys.exit(1)

    # Warn about optional API keys
    optional_apis = {
        "CLICKUP_API_TOKEN": "ClickUp",
        "YOUTUBE_API_KEY": "YouTube",
        "FRAMEIO_TOKEN": "Frame.io"
    }

    for var, service in optional_apis.items():
        if not os.getenv(var):
            logger.warning(f"{var} not set - {service} lookups will fail")


def lookup_single_url(parsed: ParsedURL) -> tuple[ParsedURL, list[str]]:
    """
    Perform lookup for a single parsed URL.

    Returns tuple of (parsed_url, list_of_values)
    """
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


def process_links(urls: list[str]) -> list[list[str]]:
    """
    Process multiple URLs in parallel and return formatted responses.

    Results are returned in the same order as input URLs.
    Each result is a list of values (e.g., [title, duration]).
    """
    # Parse all URLs first
    url_to_parsed = {}
    parsed_list = []

    for url in urls:
        parsed = parse_url(url)
        if parsed:
            url_to_parsed[url] = parsed
            parsed_list.append(parsed)
        else:
            # Keep track of unrecognized URLs
            url_to_parsed[url] = None

    # Lookup in parallel
    results = {}

    if parsed_list:
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_parsed = {
                executor.submit(lookup_single_url, p): p
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


# Initialize Slack app
load_environment()
app = App(token=os.environ["SLACK_BOT_TOKEN"])


@app.event("message")
def handle_message(event, say, client):
    """
    Handle incoming messages.
    Only respond to DMs containing URLs.
    """
    # Ignore messages from bots (including ourselves)
    if event.get("bot_id"):
        return

    # Only handle DMs (im = instant message)
    channel_type = event.get("channel_type", "")
    if channel_type != "im":
        return

    text = event.get("text", "")
    if not text:
        return

    # Extract URLs from message
    urls = extract_urls(text)

    if not urls:
        say("No URLs detected. Paste ClickUp, YouTube, or Frame.io links and I'll look them up.")
        return

    logger.info(f"Processing {len(urls)} URLs")

    # Process all URLs
    responses = process_links(urls)

    # Group values by column position (all titles together, all durations together, etc.)
    # Find max number of columns across all responses
    max_cols = max(len(values) for values in responses) if responses else 0

    # Send each column as a separate message for easy copy/paste to Sheets
    for col_idx in range(max_cols):
        column_values = []
        for url_values in responses:
            if col_idx < len(url_values):
                column_values.append(url_values[col_idx])
            else:
                column_values.append("")  # Empty if this URL has fewer columns
        say("\n".join(column_values))

    logger.info(f"Sent response for {len(urls)} URLs")


@app.event("app_mention")
def handle_mention(event, say):
    """Handle @mentions of the bot."""
    say("DM me with links to look up! I support ClickUp, YouTube, and Frame.io URLs.")


def main():
    """Start the bot using Socket Mode."""
    logger.info("Starting Payroll Link Lookup Bot...")

    handler = SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])

    logger.info("Bot is running! Press Ctrl+C to stop.")
    handler.start()


if __name__ == "__main__":
    main()
