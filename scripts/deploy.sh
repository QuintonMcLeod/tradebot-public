#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
#  deploy.sh — Unified Deployment Script for TradebotSCI
# ═══════════════════════════════════════════════════════════════════
#
#  PURPOSE:
#    One-stop script to commit, push, and mirror the TradebotSCI
#    codebase to its various remotes. Instead of manually running
#    git commands and remembering mirror URLs / auth tokens, just
#    run this script with a simple flag.
#
#  REMOTES:
#    1. origin/master  — Private development repo (gitlab.com/ultraedge/scripts)
#    2. origin/debug   — Debug/testing branch on the same private repo
#    3. tradebot-public — Public-facing mirror (gitlab.com/ultraedge/tradebot-public)
#                         Uses the publish_mirror.sh script which:
#                         • Strips secrets, logs, and sensitive config
#                         • Injects the GitLab auth token automatically
#                         • Pushes to the 'main' branch
#
#  USAGE:
#    ./scripts/deploy.sh [OPTION]
#
#    Options:
#      master     Commit all changes and push to origin/master
#      debug      Commit all changes and push to origin/debug
#      mirror     Run the public mirror script (tradebot-public, main branch)
#      all        Do all three: master + debug + mirror
#      -h, help   Show this help message
#
#  EXAMPLES:
#    ./scripts/deploy.sh master          # Push to master only
#    ./scripts/deploy.sh mirror          # Mirror to public repo only
#    ./scripts/deploy.sh all             # Push master + debug + mirror
#    ./scripts/deploy.sh                 # No args = show help
#
#  AUTHENTICATION:
#    The GitLab token (glpat-*) is stored in publish_mirror.sh and
#    is also configured in .git/config for the origin remote.
#    No manual token entry is needed.
#
#  NOTES:
#    • Always run from the repo root directory
#    • The script auto-stages ALL changes (git add -A) before commit
#    • If there are no changes to commit, the push still runs
#      (in case you have local commits not yet pushed)
#    • The mirror script excludes: .env files, logs/, data/, node_modules/
#    • tradebot-docs remote is DEPRECATED — do not use
#
# ═══════════════════════════════════════════════════════════════════

set -e

# ── Color codes for terminal output ──
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# ── Configuration ──
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
MIRROR_SCRIPT="$SCRIPT_DIR/publish_mirror.sh"
MIRROR_URL="https://gitlab.com/ultraedge/tradebot-public.git"
MIRROR_BRANCH="main"

# ── Helper Functions ──

show_help() {
    echo -e "${BOLD}${CYAN}"
    echo "  ╔══════════════════════════════════════════════════╗"
    echo "  ║        TradebotSCI Deploy Script                 ║"
    echo "  ╚══════════════════════════════════════════════════╝"
    echo -e "${NC}"
    echo -e "  ${BOLD}USAGE:${NC}  ./scripts/deploy.sh [OPTION]"
    echo ""
    echo -e "  ${BOLD}OPTIONS:${NC}"
    echo -e "    ${GREEN}master${NC}     Commit & push to origin/master"
    echo -e "    ${GREEN}debug${NC}      Commit & push to origin/debug"
    echo -e "    ${GREEN}mirror${NC}     Sync to public mirror (tradebot-public/main)"
    echo -e "    ${GREEN}all${NC}        Push master + debug + run mirror"
    echo -e "    ${YELLOW}-h, help${NC}   Show this help message"
    echo ""
    echo -e "  ${BOLD}EXAMPLES:${NC}"
    echo "    ./scripts/deploy.sh master"
    echo "    ./scripts/deploy.sh all"
    echo ""
}

# Print a section header for visual clarity in terminal output
header() {
    echo ""
    echo -e "${BOLD}${CYAN}── $1 ──${NC}"
}

# Print success message
ok() {
    echo -e "  ${GREEN}✅ $1${NC}"
}

# Print error message
fail() {
    echo -e "  ${RED}❌ $1${NC}"
}

# Print info message
info() {
    echo -e "  ${YELLOW}→ $1${NC}"
}

# ── Core Functions ──

# Stage all changes and commit with an auto-generated message.
# If there are no changes, skip the commit but still allow push.
do_commit() {
    cd "$REPO_DIR"
    header "Staging Changes"
    git add -A

    # Check if there's anything to commit
    if git diff-index --quiet HEAD -- 2>/dev/null; then
        info "No new changes to commit (existing commits may still need pushing)"
        return 0
    fi

    # Generate a commit message from the changed files
    local changed_files
    changed_files=$(git diff --cached --name-only | head -10)
    local file_count
    file_count=$(git diff --cached --name-only | wc -l)
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M')

    # Build a readable commit message
    local msg="deploy: update $timestamp ($file_count files)"

    git commit -m "$msg"
    ok "Committed: $msg"
}

# Push to a specific branch on origin.
# For the 'debug' branch, we first reset it to match master so it
# stays in sync (debug is a rolling copy of master, not independent).
# Args: $1 = branch name (e.g., "master" or "debug")
do_push() {
    local branch="$1"
    cd "$REPO_DIR"
    header "Pushing to origin/$branch"

    # If pushing debug, reset it to match master first
    if [ "$branch" = "debug" ]; then
        local current_branch
        current_branch=$(git branch --show-current)
        info "Syncing debug branch to master..."
        git branch -f debug master 2>/dev/null || {
            # Branch doesn't exist locally yet, create it
            git branch debug master
        }
        info "Debug branch now matches master"
    fi
    
    if git push origin "$branch" 2>&1; then
        ok "Pushed to origin/$branch"
    else
        # Try force push for debug (it's a rolling copy)
        if [ "$branch" = "debug" ]; then
            info "Attempting force push for debug branch..."
            if git push origin "$branch" --force 2>&1; then
                ok "Force pushed to origin/$branch"
            else
                fail "Push to origin/$branch failed"
                return 1
            fi
        else
            fail "Push to origin/$branch failed"
            return 1
        fi
    fi
}

# Run the publish_mirror.sh script to sync to the public mirror.
# This strips sensitive files and pushes to tradebot-public/main.
do_mirror() {
    cd "$REPO_DIR"
    header "Mirroring to tradebot-public (main)"
    
    if [ ! -f "$MIRROR_SCRIPT" ]; then
        fail "Mirror script not found: $MIRROR_SCRIPT"
        return 1
    fi

    if bash "$MIRROR_SCRIPT" "$MIRROR_URL" "$MIRROR_BRANCH" 2>&1; then
        ok "Mirror pushed to tradebot-public/main"
    else
        fail "Mirror push failed"
        return 1
    fi
}

# ── Main Entry Point ──

# Default to help if no arguments
if [ $# -eq 0 ]; then
    show_help
    exit 0
fi

case "$1" in
    master)
        do_commit
        do_push master
        ;;
    debug)
        do_commit
        do_push debug
        ;;
    mirror)
        do_mirror
        ;;
    all)
        do_commit
        do_push master
        do_push debug
        do_mirror
        ;;
    -h|--help|help)
        show_help
        ;;
    *)
        echo -e "${RED}Unknown option: $1${NC}"
        echo ""
        show_help
        exit 1
        ;;
esac

echo ""
echo -e "${BOLD}${GREEN}═══ Deploy complete ═══${NC}"
echo ""
