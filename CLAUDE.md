# Multi-Function Slack Bot

A pluggable Slack bot backend that supports multiple functions with user routing, access control, and function switching via slash commands.

## Project Structure

```
/home/molt/Slack Bot/
├── main.py                    # Single-bot entry point (accepts --config)
├── run_all.py                 # Multi-bot process manager
├── .env                       # Default Slack credentials (standalone mode)
├── .env.slack_bot             # Company A Slack tokens
├── .env.paired_helper         # Company B Slack tokens
├── requirements.txt           # Core dependencies
├── .venv/                     # Python virtual environment
│
├── bots/                      # Per-bot configuration
│   ├── slack_bot.json         # Company A: env file, data dir, functions
│   └── paired_helper.json     # Company B: env file, data dir, functions
│
├── core/                      # Management logic
│   ├── models.py              # BotFunction interface
│   ├── dispatcher.py          # Message routing
│   ├── storage.py             # SQLite storage (user state, permissions, logs)
│   └── plugin_loader.py       # Dynamic function discovery
│
├── data/
│   ├── slack_bot/bot.db       # Company A database
│   └── paired_helper/bot.db   # Company B database
│
├── payroll_lookup/            # Company A function
│   ├── function.py            # BotFunction implementation
│   ├── .env                   # Function-specific API keys
│   └── tools/                 # Function logic
│
├── boolean_search/            # Company B function
│   ├── function.py            # BotFunction implementation
│   ├── .env                   # Function-specific API keys
│   └── tools/                 # Function logic
│
└── <new_function>/            # Your new function goes here
    ├── function.py            # Required: implements BotFunction
    ├── .env                   # Optional: function-specific secrets
    └── tools/                 # Optional: helper modules
```

## Creating a New Function

### Step 1: Create the Function Directory

```bash
mkdir -p "/home/molt/Slack Bot/<function_name>/tools"
```

### Step 2: Implement the BotFunction Interface

Create `function.py` in your function directory with this template:

```python
"""
<Function Name> - BotFunction Implementation
"""

import sys
import logging
from pathlib import Path

# Add parent directory for core imports
PARENT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(PARENT_DIR))

from core.models import BotFunction, FunctionInfo, FunctionResponse, MessageResult

logger = logging.getLogger(__name__)


class MyFunction(BotFunction):
    """Description of what this function does."""

    def __init__(self):
        # Load function-specific environment if needed
        # from dotenv import load_dotenv
        # load_dotenv(Path(__file__).parent / ".env")
        pass

    def get_info(self) -> FunctionInfo:
        """Return metadata about this function."""
        return FunctionInfo(
            name="<function_name>",              # Must match directory name
            display_name="<Display Name>",       # Shown to users
            slash_command="/<command>",          # Command to activate
            description="Short description",     # One line
            help_text=(
                "*Help Title*\n\n"
                "Detailed help text shown when user types 'help'.\n\n"
                "*Commands:*\n"
                "- `command1` - does X\n"
                "- `command2` - does Y"
            ),
            version="1.0.0"
        )

    def handle_message(self, user_id: str, text: str, event: dict) -> FunctionResponse:
        """
        Process an incoming message.

        Args:
            user_id: Slack user ID (e.g., "U1234567890")
            text: Message text from user
            event: Full Slack event dict (contains channel, timestamp, etc.)

        Returns:
            FunctionResponse with messages to send back
        """
        # Handle help command
        if text.strip().lower() == "help":
            return FunctionResponse(
                result=MessageResult.SUCCESS,
                messages=[self.get_info().help_text]
            )

        # Your logic here
        # ...

        # Return response
        return FunctionResponse(
            result=MessageResult.SUCCESS,
            messages=["Response message 1", "Response message 2"],
            metadata={"key": "value"}  # Optional: logged for analytics
        )

    def get_welcome_message(self) -> str:
        """Message shown when user switches to this function."""
        return (
            "You're now using *<Display Name>*.\n\n"
            "Describe what the user can do here.\n\n"
            "Type `help` for more info."
        )

    # Optional: override these for setup/cleanup
    def on_activate(self, user_id: str) -> str | None:
        """Called when user switches TO this function."""
        return None  # Return a message or None

    def on_deactivate(self, user_id: str) -> None:
        """Called when user switches AWAY from this function."""
        pass


def get_function() -> BotFunction:
    """Factory function - REQUIRED. Called by plugin loader."""
    return MyFunction()
```

### Step 3: Register the Slash Command in Slack

1. Go to your Slack App settings at https://api.slack.com/apps
2. Navigate to **Slash Commands**
3. Click **Create New Command**
4. Set the command to match `slash_command` in your `FunctionInfo`
5. Set Request URL (not needed for Socket Mode, but required field)
6. Save

### Step 4: Set Permissions (Optional)

By default, new functions have no access list (nobody can use them). Configure access:

```python
# In Python, or create a setup script:
from core.storage import PermissionsStorage

perms = PermissionsStorage()

# Option A: Make function open to everyone
perms.set_function_open("<function_name>", True)

# Option B: Add specific users
perms.add_user_to_function("U1234567890", "<function_name>")
perms.add_user_to_function("U0987654321", "<function_name>")

# Option C: Make someone an admin (can access all functions)
perms.add_admin("U1234567890")
```

### Step 5: Test

```bash
cd "/home/molt/Slack Bot"
source .venv/bin/activate
python -c "
from core.plugin_loader import PluginLoader
loader = PluginLoader()
func = loader.load_function('<function_name>')
print(f'Loaded: {func.get_info().display_name}')
"
```

Then restart the bot:
```bash
python main.py
```

## Core Classes Reference

### FunctionResponse

```python
from core.models import FunctionResponse, MessageResult

# Success with messages
FunctionResponse(
    result=MessageResult.SUCCESS,
    messages=["Message 1", "Message 2"],  # Each sent as separate Slack message
    metadata={"url_count": 5}             # Optional: logged for analytics
)

# Error
FunctionResponse(
    result=MessageResult.ERROR,
    messages=["Something went wrong"],
    error="Detailed error for logs"
)

# No action needed (e.g., message didn't match any command)
FunctionResponse(
    result=MessageResult.NO_ACTION,
    messages=["I don't understand. Type 'help' for commands."]
)
```

### FunctionInfo

```python
from core.models import FunctionInfo

FunctionInfo(
    name="my_function",           # Internal name, must match directory
    display_name="My Function",   # User-facing name
    slash_command="/myfunction",  # Slash command to activate
    description="Brief desc",     # Shown in /bot-help
    help_text="Detailed help",    # Shown when user types "help"
    version="1.0.0"               # Optional
)
```

### Storage Classes

```python
from core.storage import StateStorage, PermissionsStorage, UsageLogger

# User state (which function they're using)
state = StateStorage()
state.get_current_function("U123")           # Returns function name or None
state.set_user_function("U123", "my_func")   # Set user's function

# Permissions
perms = PermissionsStorage()
perms.is_user_allowed("U123", "my_func")     # Check access
perms.set_function_open("my_func", True)     # Open to all
perms.add_user_to_function("U123", "my_func") # Add user
perms.add_admin("U123")                       # Make admin

# Usage logging (automatic, but you can query)
logger = UsageLogger()
logger.get_user_stats("U123")                # User's usage stats
logger.get_function_stats("my_func")         # Function's usage stats
```

## Database Schema

SQLite database at `data/bot.db`:

- `user_state` - Tracks each user's current function
- `function_permissions` - User-to-function access mappings
- `open_functions` - Functions open to all users
- `admins` - Admin users (access all functions)
- `usage_logs` - All function usage (messages, switches, errors)

## Global Slash Commands

These are always available:

- `/bot-help` - List available functions
- `/bot-status` - Show current function

## Example Functions

### payroll_lookup

See [payroll_lookup/function.py](payroll_lookup/function.py) for an example that:
- Processes URLs from messages
- Calls external APIs in parallel
- Returns formatted responses
- Handles errors gracefully

### boolean_search

See [boolean_search/function.py](boolean_search/function.py) for an example that:
- Parses job descriptions via LLM into structured data
- Starts with a broad query (titles + one primary skill) to guarantee results
- Shows a numbered skill picker so users can `add 2,5` or `remove 3` to refine
- Supports `add all`, `add <name>`, `remove all`, `platform seekout/linkedin`, `clear`
- Tracks per-user selected skills in conversation state (SQLite)

## Running the Bot

### Multi-bot mode (production)

Runs all bots defined in `bots/*.json` as separate processes:

```bash
cd "/home/molt/Slack Bot"
source .venv/bin/activate
python run_all.py
```

Or via systemd:
```bash
sudo systemctl start slack-bot
```

### Single-bot mode (development/testing)

Run a specific bot by its config:
```bash
python main.py --config bots/slack_bot.json
```

Or run standalone (loads `.env`, discovers all functions):
```bash
python main.py
```

## Multi-Bot Configuration

Each bot is defined by a JSON file in `bots/`:

```json
{
  "name": "my_bot",
  "env_file": ".env.my_bot",
  "data_dir": "data/my_bot",
  "functions": ["function_a", "function_b"]
}
```

| Field | Description |
|-------|-------------|
| `name` | Unique identifier (must match filename) |
| `env_file` | Path to `.env` file with SLACK_BOT_TOKEN and SLACK_APP_TOKEN |
| `data_dir` | Directory for this bot's SQLite database |
| `functions` | List of function directories this bot should load |

### Adding a new bot

1. Create `bots/<name>.json` with the config above
2. Create `.env.<name>` with the bot's Slack tokens
3. Restart the service: `sudo systemctl restart slack-bot`

## Environment Variables

**Per-bot .env** (Slack credentials):
```
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
```

**Function .env** (function-specific):
```
API_KEY=...
OTHER_SECRET=...
```

Load function secrets in your `__init__`:
```python
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")
```
