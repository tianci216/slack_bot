# Multi-Function Slack Bot

A pluggable Slack bot backend that supports multiple functions with user routing, access control, and function switching via slash commands. Each bot runs in its own Docker container; each function lives in its own git repo.

## Project Structure

```
/home/molt/Slack Bot/
├── main.py                    # Bot entry point
├── Dockerfile                 # Container image definition
├── docker-compose.yml         # Multi-container orchestration
├── docker-entrypoint.sh       # Installs function deps on container start
├── deploy.sh                  # Pull function repos + rebuild containers
├── requirements.txt           # Core dependencies
│
├── access.slack_bot.json      # Bot A: function list + access control
├── access.paired_helper.json  # Bot B: function list + access control
├── .env.slack_bot             # Bot A: Slack tokens
├── .env.paired_helper         # Bot B: Slack tokens
│
├── core/                      # Framework logic
│   ├── models.py              # BotFunction interface
│   ├── dispatcher.py          # Message routing
│   ├── storage.py             # SQLite storage (user state, permissions, logs)
│   └── plugin_loader.py       # Dynamic function discovery
│
├── functions/                 # Function repos (gitignored, cloned on server)
│   ├── payroll_lookup/
│   ├── contact_finder/
│   ├── description_writer/
│   └── boolean_search/
│
└── data/                      # Per-bot SQLite databases (Docker volumes)
    ├── slack_bot/bot.db
    └── paired_helper/bot.db
```

## Creating a New Function

### Step 1: Create the Function Repository

Create a new git repo for your function:

```bash
mkdir <function_name>
cd <function_name>
git init
mkdir tools
```

### Step 2: Implement the BotFunction Interface

Create `function.py` with this template:

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
        if text.strip().lower() == "help":
            return FunctionResponse(
                result=MessageResult.SUCCESS,
                messages=[self.get_info().help_text]
            )

        # Your logic here
        return FunctionResponse(
            result=MessageResult.SUCCESS,
            messages=["Response message"],
            metadata={"key": "value"}  # Optional: logged for analytics
        )

    def get_welcome_message(self) -> str:
        """Message shown when user switches to this function."""
        return (
            "You're now using *<Display Name>*.\n\n"
            "Describe what the user can do here.\n\n"
            "Type `help` for more info."
        )

    def on_activate(self, user_id: str) -> str | None:
        """Called when user switches TO this function."""
        return None

    def on_deactivate(self, user_id: str) -> None:
        """Called when user switches AWAY from this function."""
        pass


def get_function() -> BotFunction:
    """Factory function - REQUIRED. Called by plugin loader."""
    return MyFunction()
```

### Step 3: Add Function Dependencies

Create `requirements.txt` in your function repo with any function-specific packages. These are installed automatically when the Docker container starts.

### Step 4: Clone into the Server

```bash
cd "/home/molt/Slack Bot/functions"
git clone <your-function-repo-url>
```

### Step 5: Register in Bot Config

Add your function to the appropriate `access.*.json` file:

```json
{
  "functions": ["existing_func", "your_new_function"],
  "admins": ["U123"],
  "open_functions": [],
  "function_permissions": {
    "your_new_function": ["U456", "U789"]
  }
}
```

### Step 6: Register the Slash Command in Slack

1. Go to your Slack App settings at https://api.slack.com/apps
2. Navigate to **Slash Commands**
3. Click **Create New Command**
4. Set the command to match `slash_command` in your `FunctionInfo`
5. Set Request URL (not needed for Socket Mode, but required field)
6. Save

### Step 7: Deploy

```bash
cd "/home/molt/Slack Bot"
docker compose up --build -d
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

# No action needed
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

SQLite database at `data/<bot_name>/bot.db`:

- `user_state` - Tracks each user's current function
- `function_permissions` - User-to-function access mappings
- `open_functions` - Functions open to all users
- `admins` - Admin users (access all functions)
- `usage_logs` - All function usage (messages, switches, errors)

## Global Slash Commands

These are always available:

- `/bot-help` - List available functions
- `/bot-status` - Show current function

## Bot Configuration

Each bot is defined by two files:

**`access.<bot_name>.json`** - which functions to load and who can use them:
```json
{
  "functions": ["function_a", "function_b"],
  "admins": ["U123"],
  "open_functions": ["function_a"],
  "function_permissions": {
    "function_b": ["U456"]
  }
}
```

**`.env.<bot_name>`** - Slack credentials:
```
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
```

### Adding a New Bot

1. Create `.env.<name>` with the bot's Slack tokens
2. Create `access.<name>.json` with the function list and permissions
3. Add a new service to `docker-compose.yml`:
   ```yaml
   new-bot:
     build: .
     image: slack-bot:latest
     restart: unless-stopped
     env_file: .env.<name>
     volumes:
       - ./functions:/app/functions:ro
       - ./data/<name>:/app/data
       - ./access.<name>.json:/app/access.json:ro
   ```
4. Run `docker compose up --build -d`

## Running the Bot

### Production (Docker)

```bash
cd "/home/molt/Slack Bot"
docker compose up --build -d
```

Manage containers:
```bash
docker compose ps                # Status
docker compose logs -f           # Live logs
docker compose logs slack-bot    # Logs for one bot
docker compose restart slack-bot # Restart one bot
docker compose down              # Stop all
```

### Deploying Updates

For core framework changes:
```bash
git pull
docker compose up --build -d
```

For function updates:
```bash
cd functions/<function_name>
git pull
cd ../..
docker compose up --build -d
```

Or use the deploy script:
```bash
./deploy.sh
```

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
