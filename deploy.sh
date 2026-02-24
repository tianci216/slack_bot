#!/bin/bash
set -e

BOT_ROOT="/home/molt/Slack Bot"
FUNCTIONS_DIR="$BOT_ROOT/functions"

echo "=== Slack Bot Deploy ==="

mkdir -p "$FUNCTIONS_DIR"

# Clone or pull each function repo
# Replace URLs with actual remote URLs once each function has its own repo
declare -A FUNCTION_REPOS=(
    ["payroll_lookup"]="git@github.com:your-org/payroll_lookup.git"
    ["contact_finder"]="git@github.com:your-org/contact_finder.git"
    ["description_writer"]="git@github.com:your-org/description_writer.git"
    ["boolean_search"]="git@github.com:your-org/boolean_search.git"
)

for name in "${!FUNCTION_REPOS[@]}"; do
    url="${FUNCTION_REPOS[$name]}"
    dest="$FUNCTIONS_DIR/$name"
    if [ -d "$dest/.git" ]; then
        echo "Pulling $name..."
        git -C "$dest" pull --ff-only
    else
        echo "Cloning $name..."
        git clone "$url" "$dest"
    fi
done

# Rebuild image and restart containers
cd "$BOT_ROOT"
docker compose build
docker compose up -d

echo "=== Deploy complete ==="
docker compose ps
