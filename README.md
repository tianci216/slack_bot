# Multi-Function Slack Bot

A pluggable Slack bot backend that supports multiple functions with user routing, access control, and function switching via slash commands.

## Features

- **Multi-Function Support** - Each subfolder is a separate function that users can switch between
- **User Routing** - Tracks which function each user is currently using and routes messages accordingly
- **Access Control** - Allow-list management for controlling who can access which functions
- **Slash Command Switching** - Users switch functions via slash commands (e.g., `/payroll`)
- **Usage Logging** - SQLite database tracks all function usage for analytics
- **Socket Mode** - No public URL required, works behind firewalls

## Prerequisites

- Python 3.10+
- A Slack App with:
  - Bot Token (`xoxb-...`)
  - App-Level Token (`xapp-...`) with `connections:write` scope
  - Socket Mode enabled

## Deployment on a New Server

### 1. Clone/Copy the Project

```bash
# Copy project to server
scp -r "Slack Bot" user@server:/home/user/

# Or clone from git
git clone <repo-url> "/home/user/Slack Bot"
```

### 2. Set Up Python Environment

```bash
cd "/home/user/Slack Bot"

# Create virtual environment
python3 -m venv .venv

# Activate environment
source .venv/bin/activate

# Install core dependencies
pip install -r requirements.txt

# Install function-specific dependencies
pip install -r payroll_lookup/requirements.txt
```

### 3. Configure Environment Variables

Create `.env` file in the project root:

```bash
cat > .env << 'EOF'
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token
EOF
```

For function-specific credentials (e.g., API keys), create `.env` in each function folder:

```bash
cat > payroll_lookup/.env << 'EOF'
CLICKUP_API_TOKEN=pk_...
YOUTUBE_API_KEY=AIza...
FRAMEIO_TOKEN=fio-u-...
EOF
```

### 4. Configure Slack App

In your [Slack App settings](https://api.slack.com/apps):

1. **Enable Socket Mode**
   - Settings → Socket Mode → Enable

2. **Add Bot Token Scopes** (OAuth & Permissions)
   - `chat:write`
   - `im:history`
   - `im:read`
   - `im:write`
   - `users:read`

3. **Subscribe to Bot Events** (Event Subscriptions)
   - `message.im`
   - `app_mention`
   - `app_home_opened`

4. **Create Slash Commands**
   - `/payroll` - Switch to Payroll Link Lookup
   - `/bot-help` - Show available functions
   - `/bot-status` - Show current function

5. **Install App to Workspace**

### 5. Set Up Permissions

```bash
source .venv/bin/activate
python << 'EOF'
from core.storage import PermissionsStorage

perms = PermissionsStorage()

# Make payroll_lookup open to all users
perms.set_function_open("payroll_lookup", True)

# Or add specific users
# perms.add_user_to_function("U1234567890", "payroll_lookup")

# Add an admin (optional)
# perms.add_admin("U1234567890")

print("Permissions configured!")
EOF
```

### 6. Test the Bot

```bash
source .venv/bin/activate
python main.py
```

You should see:
```
INFO - Starting Multi-Function Slack Bot...
INFO - Loaded 1 functions
INFO - Bot is running! Press Ctrl+C to stop.
```

## Running as a Service (Production)

### Install Systemd Service

```bash
# Copy service file
sudo cp slack-bot.service /etc/systemd/system/

# Update paths in service file if needed
sudo nano /etc/systemd/system/slack-bot.service

# Reload systemd
sudo systemctl daemon-reload

# Enable auto-start on boot
sudo systemctl enable slack-bot

# Start the bot
sudo systemctl start slack-bot
```

### Service Management

```bash
sudo systemctl start slack-bot      # Start the bot
sudo systemctl stop slack-bot       # Stop the bot
sudo systemctl restart slack-bot    # Restart the bot
sudo systemctl status slack-bot     # Check status

# View logs
journalctl -u slack-bot -f          # Live logs
journalctl -u slack-bot -n 100      # Last 100 lines
```

## Usage

### For Users

1. **DM the bot** - Send a direct message to start
2. **Select a function** - Use `/bot-help` to see available functions
3. **Switch functions** - Use the slash command (e.g., `/payroll`)
4. **Get help** - Type `help` within any function

### Slash Commands

| Command | Description |
|---------|-------------|
| `/bot-help` | List all available functions |
| `/bot-status` | Show your current function |
| `/payroll` | Switch to Payroll Link Lookup |

## Project Structure

```
Slack Bot/
├── main.py                 # Bot entry point
├── .env                    # Slack credentials
├── requirements.txt        # Core dependencies
├── slack-bot.service       # Systemd service file
├── CLAUDE.md               # Guide for creating new functions
│
├── core/                   # Core infrastructure
│   ├── models.py           # BotFunction interface
│   ├── dispatcher.py       # Message routing
│   ├── storage.py          # SQLite storage
│   └── plugin_loader.py    # Function discovery
│
├── data/
│   └── bot.db              # SQLite database
│
└── payroll_lookup/         # Example function
    ├── function.py         # BotFunction implementation
    ├── .env                # Function-specific secrets
    └── tools/              # Function logic
```

## Adding New Functions

See [CLAUDE.md](CLAUDE.md) for detailed instructions on creating new functions.

Quick overview:
1. Create a new folder: `mkdir my_function`
2. Create `my_function/function.py` implementing `BotFunction`
3. Add slash command in Slack App settings
4. Set permissions
5. Restart the bot

## Troubleshooting

### Bot not responding to DMs

- Check bot has `im:history`, `im:read`, `im:write` scopes
- Verify `message.im` event subscription is enabled
- Check logs: `journalctl -u slack-bot -n 50`

### Slash command not working

- Verify command is registered in Slack App settings
- Check the command matches `slash_command` in function's `FunctionInfo`
- Restart bot after adding new functions

### Permission denied

- User needs to be added to function's allow list
- Or function needs to be set as open: `perms.set_function_open("func_name", True)`
- Or user needs to be an admin: `perms.add_admin("U1234567890")`

### View database

```bash
sqlite3 data/bot.db
.tables
SELECT * FROM user_state;
SELECT * FROM function_permissions;
SELECT * FROM usage_logs ORDER BY timestamp DESC LIMIT 10;
.quit
```

## License

Internal use only.
