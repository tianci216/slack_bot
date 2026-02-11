"""
Multi-Function Slack Bot - Main Entry Point

Central bot that:
- Routes DMs to user's current function
- Handles slash commands for function switching
- Manages global bot events
"""

import os
import sys
import json
import argparse
import logging
from pathlib import Path
from dotenv import load_dotenv

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

# Add current directory to path for core imports
BOT_DIR = Path(__file__).parent
sys.path.insert(0, str(BOT_DIR))

from core.dispatcher import Dispatcher

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Multi-Function Slack Bot")
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to bot config JSON file (e.g., bots/slack_bot.json)"
    )
    return parser.parse_args()


def load_environment(env_file: str | None = None):
    """Load and validate environment variables."""
    if env_file:
        env_path = BOT_DIR / env_file
    else:
        env_path = BOT_DIR / ".env"
    load_dotenv(env_path)

    required_vars = ["SLACK_BOT_TOKEN", "SLACK_APP_TOKEN"]
    missing = [var for var in required_vars if not os.getenv(var)]

    if missing:
        logger.error(
            f"Missing required environment variables: {', '.join(missing)}"
        )
        sys.exit(1)


# Parse config and initialize
args = parse_args()
config = None

if args.config:
    config_path = BOT_DIR / args.config
    with open(config_path) as f:
        config = json.load(f)
    logger.info(f"Loaded bot config: {config.get('name', args.config)}")

load_environment(config.get("env_file") if config else None)
app = App(token=os.environ["SLACK_BOT_TOKEN"])

_data_dir = BOT_DIR / config["data_dir"] if config and "data_dir" in config else None
_allowed_functions = config.get("functions") if config else None
dispatcher = Dispatcher(allowed_functions=_allowed_functions, data_dir=_data_dir)

# Sync access config from bot JSON if present
if config and "access" in config:
    dispatcher.permissions.sync_from_config(config["access"])


# ============================================================================
# SLASH COMMANDS
# ============================================================================

def create_slash_command_handler(function_name: str):
    """Factory to create slash command handler for a function."""

    def handler(ack, command, say):
        ack()
        user_id = command["user_id"]
        logger.info(f"User {user_id} requested function '{function_name}'")
        dispatcher.switch_user_function(user_id, function_name, say)

    return handler


def register_slash_commands():
    """Register slash commands for all loaded functions."""
    for func_name, func in dispatcher.functions.items():
        info = func.get_info()
        command = info.slash_command

        handler = create_slash_command_handler(func_name)
        app.command(command)(handler)

        logger.info(f"Registered slash command: {command} -> {func_name}")


@app.command("/bot-help")
def handle_help_command(ack, command, say):
    """Show available functions and their commands."""
    ack()

    user_id = command["user_id"]
    functions = dispatcher.get_available_functions_for_user(user_id)

    if not functions:
        say("You don't have access to any functions. Contact an administrator.")
        return

    lines = ["*Available Functions:*\n"]
    for func in functions:
        info = func.get_info()
        lines.append(f"*{info.display_name}*")
        lines.append(f"  Command: `{info.slash_command}`")
        lines.append(f"  {info.description}\n")

    # Show current function
    current = dispatcher.state_storage.get_current_function(user_id)
    if current:
        current_func = dispatcher.get_function(current)
        if current_func:
            lines.append(
                f"_Current function: {current_func.get_info().display_name}_"
            )
    else:
        lines.append("_No function selected. Use a command above to get started._")

    say("\n".join(lines))


@app.command("/bot-status")
def handle_status_command(ack, command, say):
    """Show current function status."""
    ack()

    user_id = command["user_id"]
    current = dispatcher.state_storage.get_current_function(user_id)

    if current:
        func = dispatcher.get_function(current)
        if func:
            info = func.get_info()
            say(
                f"You're currently using *{info.display_name}*.\n\n"
                "Type `help` for function-specific help."
            )
        else:
            say(
                "Your selected function is no longer available. "
                "Use `/bot-help` to see options."
            )
    else:
        say("No function selected. Use `/bot-help` to see available options.")


# ============================================================================
# EVENT HANDLERS
# ============================================================================

@app.event("message")
def handle_message(event, say, client):
    """Handle incoming messages. Only respond to DMs."""
    # Ignore bot messages
    if event.get("bot_id"):
        return

    # Only handle DMs
    channel_type = event.get("channel_type", "")
    if channel_type != "im":
        return

    text = event.get("text", "")
    if not text:
        return

    user_id = event.get("user")
    if not user_id:
        return

    dispatcher.handle_dm(user_id, text, event, say)


@app.event("app_mention")
def handle_mention(event, say):
    """Handle @mentions of the bot."""
    say("DM me to get started, or use `/bot-help` to see available functions.")


@app.event("app_home_opened")
def handle_app_home(event, client):
    """Update App Home tab when opened."""
    user_id = event["user"]

    functions = dispatcher.get_available_functions_for_user(user_id)
    current = dispatcher.state_storage.get_current_function(user_id)

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "Multi-Function Bot"}
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "Welcome! Use slash commands to switch between functions."
            }
        },
        {"type": "divider"},
    ]

    if current:
        func = dispatcher.get_function(current)
        if func:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Current Function:* {func.get_info().display_name}"
                }
            })

    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": "*Available Functions:*"}
    })

    for func in functions:
        info = func.get_info()
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*{info.display_name}*\n"
                    f"{info.description}\n"
                    f"Command: `{info.slash_command}`"
                )
            }
        })

    try:
        client.views_publish(
            user_id=user_id,
            view={"type": "home", "blocks": blocks}
        )
    except Exception as e:
        logger.error(f"Failed to publish app home: {e}")


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Start the bot."""
    logger.info("Starting Multi-Function Slack Bot...")

    # Register slash commands for all loaded functions
    register_slash_commands()

    handler = SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])

    logger.info(f"Loaded {len(dispatcher.functions)} functions")
    logger.info("Bot is running! Press Ctrl+C to stop.")
    handler.start()


if __name__ == "__main__":
    main()
