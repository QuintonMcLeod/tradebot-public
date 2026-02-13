#!/usr/bin/env bash
set -e

# Usage: ./scripts/publish_mirror.sh <REMOTE_URL> [BRANCH]

# 1. Config
# NOTE: GitLab Token found in .git/config: glpat-cP_TZ3UHPm443qzMJCyo
# This token is required for pushing to the public mirror.
GITLAB_TOKEN="glpat-cP_TZ3UHPm443qzMJCyo"

RAW_URL="${1:-}"
BRANCH="${2:-main}"
EXPORT_DIR="public_mirror"

if [ -z "$RAW_URL" ]; then
    echo "Usage: ./scripts/publish_mirror.sh <REMOTE_URL> [BRANCH]"
    exit 1
fi

# Inject token into URL if not already present
if [[ "$RAW_URL" == *"gitlab.com"* ]] && [[ "$RAW_URL" != *"@"* ]]; then
    REMOTE_URL="${RAW_URL/https:\/\//https:\/\/oauth2:$GITLAB_TOKEN@}"
    echo "🔑 Injected GitLab token into remote URL."
else
    REMOTE_URL="$RAW_URL"
fi

echo "--- Syncing Code + Docs to '$EXPORT_DIR' and pushing to '$REMOTE_URL' ---"

# 2. Prepare Export Directory
# We treat this as a persistent git repo so we can push updates
if [ ! -d "$EXPORT_DIR" ]; then
    echo "Initializing public mirror directory: $EXPORT_DIR"
    mkdir -p "$EXPORT_DIR"
    cd "$EXPORT_DIR"
    git init
    git checkout -b "$BRANCH" || git checkout "$BRANCH"
    git remote add origin "$REMOTE_URL"
    cd ..
else
    # Update remote URL if changed
    cd "$EXPORT_DIR"
    if git remote | grep -q "^origin$"; then
        git remote set-url origin "$REMOTE_URL"
    else
        git remote add origin "$REMOTE_URL"
    fi
    # Fetch to avoid conflicts if possible, though we usually overwrite
    git fetch origin || true
    cd ..
fi

# 3. Sync Safe Files (RSYNC)
# We exclude hidden files, configs, logs, and sensitive data
echo "Syncing files..."
rsync -av --delete \
    --exclude='.git*' \
    --exclude='__pycache__' \
    --exclude='.venv' \
    --include='.env.example' \
    --exclude='.env*' \
    --exclude='node_modules/' \
    --exclude='config/broker_*.yaml' \
    --exclude='logs/' \
    --exclude='data/' \
    --exclude='scripts/deploy.sh' \
    --exclude='Trash/' \
    --exclude='backtest_output*.log' \
    --exclude='public_mirror/' \
    --include='src/***' \
    --include='Documentation/***' \
    --include='scripts/***' \
    --include='tools/***' \
    --include='config/' \
    --include='config/settings_*.yaml' \
    --include='config.json' \
    --include='README.md' \
    --include='pyproject.toml' \
    --include='poetry.lock' \
    --exclude='*' \
    . "$EXPORT_DIR/"

# PARANOID CLEANUP: Ensure no .env files ever get committed
rm -f "$EXPORT_DIR/.env" "$EXPORT_DIR/.env.prod" "$EXPORT_DIR/.env.staging"
echo "🔒 Secured: Removed .env files from export directory."

# 4. Commit and Push
cd "$EXPORT_DIR"

# Config for this repo if not set
if [ -z "$(git config user.name)" ]; then
    git config user.name "Tradebot Automation"
    git config user.email "bot@tradebot"
fi

echo "Staging files..."
git add .

if git diff-index --quiet HEAD --; then
    echo "No changes to publish."
else
    echo "Committing changes..."
    git commit -m "Update public mirror: $(date '+%Y-%m-%d %H:%M:%S')"
    
    echo "Pushing to public remote..."
    git push origin "$BRANCH"
fi

echo "✅ Success! Public mirror updated at $REMOTE_URL"
