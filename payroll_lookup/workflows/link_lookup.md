# Link Lookup Workflow

## Objective
Allow users to look up information from ClickUp, YouTube, and Frame.io links via Slack DM without needing direct access to confidential payroll sheets.

## User Flow
1. User opens a DM with the bot
2. User pastes one or more links (can be mixed types)
3. Bot responds with formatted data ready to paste into Google Sheets

## Supported Services

### ClickUp
- **URL Formats:**
  - `https://app.clickup.com/t/{task_id}`
  - `https://app.clickup.com/{team_id}/v/li/{list_id}?task={task_id}`
- **Returns:** Task name, Status
- **Output:** `{task_name}\t{status}`

### YouTube
- **URL Formats:**
  - `https://www.youtube.com/watch?v={video_id}`
  - `https://youtu.be/{video_id}`
- **Returns:** Video title, Duration
- **Output:** `{title}\t{duration}`

### Frame.io
- **URL Formats:**
  - `https://f.io/{short_code}` (short links, most common)
  - `https://app.frame.io/reviews/{review_link_id}`
  - `https://app.frame.io/player/{asset_id}`
- **Returns:** Asset name, Duration, Status label
- **Output:** `{name}\t{duration}\t{status}`

## Response Format
- Results returned in same order as input
- Tab-separated for direct paste to Google Sheets
- Each line = one row in Sheets
- Errors prefixed with `ERROR:`

## Running the Bot

### Prerequisites
1. Python 3.10+
2. Virtual environment (recommended)
3. API credentials in `.env` file

### Setup
```bash
cd /home/molt/Slack\ Bot/payroll_lookup

# Using uv (faster, already installed)
~/.local/bin/uv venv
source .venv/bin/activate
~/.local/bin/uv pip install -r requirements.txt

# Or using standard venv (requires python3-venv package)
# python -m venv .venv
# source .venv/bin/activate
# pip install -r requirements.txt
```

### Configure Environment
Copy `.env.example` to `.env` and fill in credentials:
```bash
cp .env.example .env
nano .env
```

### Start the Bot
```bash
cd /home/molt/Slack\ Bot/payroll_lookup
source .venv/bin/activate
python tools/slack_bot.py
```

### Running as a Service (systemd)
Create `/etc/systemd/system/payroll-lookup-bot.service`:
```ini
[Unit]
Description=Payroll Link Lookup Slack Bot
After=network.target

[Service]
Type=simple
User=molt
WorkingDirectory=/home/molt/Slack Bot/payroll_lookup
ExecStart=/home/molt/Slack Bot/payroll_lookup/.venv/bin/python tools/slack_bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable payroll-lookup-bot
sudo systemctl start payroll-lookup-bot
```

## API Setup

### Slack App Setup
1. Go to https://api.slack.com/apps
2. Create New App > From scratch
3. Name: "Payroll Link Lookup" (or similar)
4. Select your workspace

**Enable Socket Mode:**
1. Settings > Socket Mode > Enable
2. Generate App-Level Token with `connections:write` scope
3. Save as `SLACK_APP_TOKEN` in `.env`

**Bot Token Scopes (OAuth & Permissions):**
- `chat:write` - Send messages
- `im:history` - Read DM messages
- `im:read` - Access DM channel info

**Event Subscriptions:**
1. Enable Events
2. Subscribe to bot events: `message.im`

**Install App:**
1. OAuth & Permissions > Install to Workspace
2. Copy Bot User OAuth Token as `SLACK_BOT_TOKEN`

### ClickUp API
1. Go to ClickUp Settings > Apps
2. Generate Personal API Token
3. Save as `CLICKUP_API_TOKEN`

### YouTube Data API
1. Go to Google Cloud Console
2. Create or select a project
3. Enable YouTube Data API v3
4. Create API Key (no OAuth needed)
5. Save as `YOUTUBE_API_KEY`

### Frame.io API
1. Go to Frame.io Developer Settings
2. Create Developer Token
3. Ensure read access to relevant projects
4. Save as `FRAMEIO_TOKEN`

## Troubleshooting

### Bot not responding
- Check bot is running: `systemctl status payroll-lookup-bot`
- Check logs: `journalctl -u payroll-lookup-bot -f`
- Verify Socket Mode is enabled in Slack app

### API errors
- Verify tokens in `.env` are correct
- Check API quotas (YouTube has daily limits)
- Ensure Frame.io token has access to the projects

### URL not recognized
- Check URL format matches supported patterns
- Frame.io short links require network access to resolve

## Maintenance

### Logs
- Bot logs to stdout/stderr
- When running as systemd service, use `journalctl -u payroll-lookup-bot`

### Updates
```bash
cd /home/molt/Slack\ Bot/payroll_lookup
source .venv/bin/activate
~/.local/bin/uv pip install -U -r requirements.txt
sudo systemctl restart payroll-lookup-bot
```
