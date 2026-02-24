# Multi-Function Slack Bot

A pluggable Slack bot backend that supports multiple functions with user routing, access control, and function switching via slash commands. Each bot runs in its own Docker container; each function lives in its own git repo.

## Features

- **Multi-Function Support** - Each function is a separate repo, discovered automatically from `functions/`
- **User Routing** - Tracks which function each user is currently using and routes messages accordingly
- **Access Control** - JSON-based config controls who can access which functions
- **Slash Command Switching** - Users switch functions via slash commands (e.g., `/payroll`)
- **Usage Logging** - SQLite database tracks all function usage for analytics
- **Socket Mode** - No public URL required, works behind firewalls
- **Docker Deployment** - Each bot runs in its own isolated container

## Prerequisites

- Docker and Docker Compose
- A Slack App with:
  - Bot Token (`xoxb-...`)
  - App-Level Token (`xapp-...`) with `connections:write` scope
  - Socket Mode enabled

## Deployment on a New Server

### 1. Clone the Project

```bash
git clone <repo-url> "/home/user/Slack Bot"
cd "/home/user/Slack Bot"
```

### 2. Clone Function Repos

```bash
cd functions
git clone <payroll-lookup-repo>    payroll_lookup
git clone <boolean-search-repo>    boolean_search
# ... etc
cd ..
```

### 3. Configure Environment Variables

Create `.env.<bot_name>` for each bot:

```bash
cat > .env.slack_bot << 'EOF'
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token
EOF
```

For function-specific credentials (API keys), create `.env` in each function's directory.

### 4. Configure Access Control

Edit `access.<bot_name>.json` for each bot:

```json
{
  "functions": ["payroll_lookup", "contact_finder"],
  "admins": ["U1234567890"],
  "open_functions": [],
  "function_permissions": {
    "payroll_lookup": ["U0987654321"]
  }
}
```

### 5. Configure Slack App

In your [Slack App settings](https://api.slack.com/apps):

1. **Enable Socket Mode**
   - Settings > Socket Mode > Enable

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

### 6. Build and Run

```bash
docker compose up --build -d
```

Verify:
```bash
docker compose logs -f
```

You should see:
```
INFO - Loaded 2 functions: ['payroll_lookup', 'contact_finder']
INFO - Bot is running! Press Ctrl+C to stop.
```

## Container Management

```bash
docker compose ps                # Status of all containers
docker compose logs -f           # Live logs (all bots)
docker compose logs slack-bot    # Logs for one bot
docker compose restart slack-bot # Restart one bot
docker compose down              # Stop all
docker compose up --build -d     # Rebuild and restart
```

## Deploying Updates

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

Or use the deploy script to pull all repos and rebuild:
```bash
./deploy.sh
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
├── main.py                    # Bot entry point
├── Dockerfile                 # Container image definition
├── docker-compose.yml         # Multi-container orchestration
├── docker-entrypoint.sh       # Installs function deps on start
├── deploy.sh                  # Pull repos + rebuild containers
├── requirements.txt           # Core dependencies
│
├── access.slack_bot.json      # Bot A config (functions + permissions)
├── access.paired_helper.json  # Bot B config
├── .env.slack_bot             # Bot A Slack tokens
├── .env.paired_helper         # Bot B Slack tokens
│
├── core/                      # Framework
│   ├── models.py              # BotFunction interface
│   ├── dispatcher.py          # Message routing
│   ├── storage.py             # SQLite storage
│   └── plugin_loader.py       # Function discovery
│
├── functions/                 # Function repos (gitignored)
│   ├── payroll_lookup/
│   ├── contact_finder/
│   ├── description_writer/
│   └── boolean_search/
│
└── data/                      # Per-bot databases (Docker volumes)
    ├── slack_bot/bot.db
    └── paired_helper/bot.db
```

## Adding New Functions

See [CLAUDE.md](CLAUDE.md) for detailed instructions on creating new functions.

Quick overview:
1. Create a new git repo with `function.py` implementing `BotFunction`
2. Clone it into `functions/`
3. Add the function name to `access.<bot>.json`
4. Register the slash command in Slack App settings
5. Run `docker compose up --build -d`

## Troubleshooting

### Bot not responding to DMs

- Check bot has `im:history`, `im:read`, `im:write` scopes
- Verify `message.im` event subscription is enabled
- Check logs: `docker compose logs slack-bot`

### Slash command not working

- Verify command is registered in Slack App settings
- Check the command matches `slash_command` in function's `FunctionInfo`
- Restart container after adding new functions

### Permission denied

- User needs to be added to function's access list in `access.<bot>.json`
- Or function needs to be in `open_functions` list
- Or user needs to be in `admins` list

### View database

```bash
sqlite3 data/slack_bot/bot.db
.tables
SELECT * FROM user_state;
SELECT * FROM function_permissions;
SELECT * FROM usage_logs ORDER BY timestamp DESC LIMIT 10;
.quit
```

## License

Internal use only.
