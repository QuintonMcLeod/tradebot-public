#!/usr/bin/env bash
set -e

# Usage: ./scripts/publish_folder.sh <FOLDER_PATH> <REMOTE_URL> [BRANCH]

FOLDER="${1:-Documentation}"
REMOTE_URL="${2:-}"
REMOTE_NAME="public_docs"
BRANCH="${3:-main}"

if [ -z "$REMOTE_URL" ]; then
    echo "Usage: ./scripts/publish_folder.sh <FOLDER_PATH> <REMOTE_URL> [BRANCH]"
    echo ""
    echo "Example: ./scripts/publish_folder.sh Documentation https://gitlab.com/username/my-public-docs.git"
    exit 1
fi

echo "--- Publishing '$FOLDER' to '$REMOTE_URL' ($BRANCH) ---"

# 1. Check if remote exists, if not add it
if ! git remote | grep -q "^${REMOTE_NAME}$"; then
    echo "Adding remote '$REMOTE_NAME'..."
    git remote add "$REMOTE_NAME" "$REMOTE_URL"
else
    # Update URL just in case
    echo "Updating remote '$REMOTE_NAME' URL..."
    git remote set-url "$REMOTE_NAME" "$REMOTE_URL"
fi

# 2. Verify folder exists
if [ ! -d "$FOLDER" ]; then
    echo "Error: Folder '$FOLDER' does not exist."
    exit 1
fi

# 3. Push using git subtree
echo "Pushing folder content to remote branch '$BRANCH'..."
echo "NOTE: This might ask for your GitLab credentials."

# Using split+push pattern which is often more robust for repeated pushes than just push
# Logic: Split the folder into a temporary branch, then push that branch
SPLIT_BRANCH="temp_publish_${FOLDER//\//_}"

echo "Splitting '$FOLDER' into temporary branch '$SPLIT_BRANCH'..."
git subtree split --prefix="$FOLDER" -b "$SPLIT_BRANCH"

echo "Pushing '$SPLIT_BRANCH' to '$REMOTE_NAME/$BRANCH'..."
git push "$REMOTE_NAME" "$SPLIT_BRANCH:$BRANCH" --force

echo "Cleaning up temporary branch..."
git branch -D "$SPLIT_BRANCH"

echo "✅ Success! '$FOLDER' is now live at $REMOTE_URL"
