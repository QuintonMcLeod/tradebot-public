#!/usr/bin/env python3
import subprocess
import json
import urllib.request
import urllib.error
import sys
import re

# REPO CONFIG
PUBLIC_REPO_NAME = "tradebot-public"
PUBLIC_REPO_DESC = "Open Source edition of Tradebot SCI (Code + Docs)"

def get_git_remote_url():
    try:
        url = subprocess.check_output(["git", "remote", "get-url", "origin"]).decode().strip()
        return url
    except subprocess.CalledProcessError:
        return None

def extract_credentials(url):
    # Match pattern: https://oauth2:TOKEN@gitlab.com/...
    match = re.search(r"https://[^:]+:([^@]+)@gitlab.com", url)
    if match:
        return match.group(1)
    return None

def create_gitlab_repo(token, repo_name):
    url = "https://gitlab.com/api/v4/projects"
    data = {
        "name": repo_name,
        "visibility": "public",
        "description": PUBLIC_REPO_DESC,
        "initialize_with_readme": False
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode('utf-8'),
        headers={
            "PRIVATE-TOKEN": token,
            "Content-Type": "application/json"
        },
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode())
            print(f"✅ Repository created: {result['web_url']}")
            return result['http_url_to_repo']
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        if e.code == 400 and ("already taken" in body.lower() or "has already been taken" in body.lower()):
            print(f"⚠️  Repo '{repo_name}' exists. Reusing it...")
            return get_existing_repo(token, repo_name)
        print(f"❌ Failed to create repo: {e.code} - {body}")
        return None

def get_existing_repo(token, repo_name):
    url = f"https://gitlab.com/api/v4/projects?search={repo_name}&owned=true"
    req = urllib.request.Request(url, headers={"PRIVATE-TOKEN": token})
    try:
        with urllib.request.urlopen(req) as response:
            projects = json.loads(response.read().decode())
            for p in projects:
                if p['name'] == repo_name:
                    return p['http_url_to_repo']
            return None
    except Exception as e:
        print(f"❌ Error checking repos: {e}")
        return None

def main():
    print("🔍 Reading git credentials...")
    remote_url = get_git_remote_url()
    if not remote_url:
        print("❌ No git remote found.")
        sys.exit(1)

    token = extract_credentials(remote_url)
    if not token:
        print("❌ No API token found in git remote. Ensure you cloned with a PAT/OAuth token.")
        sys.exit(1)

    print(f"🚀 Ensuring public repo '{PUBLIC_REPO_NAME}' exists...")
    target_url = create_gitlab_repo(token, PUBLIC_REPO_NAME)
    
    if not target_url:
        print("❌ Could not get target repo URL.")
        sys.exit(1)
        
    # Inject auth token for push
    if "https://" in target_url and "@" not in target_url:
        auth_url = target_url.replace("https://", f"https://oauth2:{token}@", 1)
    else:
        auth_url = target_url

    print(f"📦 Mirroring Code + Docs to {target_url}...")
    
    cmd = ["./scripts/publish_mirror.sh", auth_url, "main"]
    try:
        subprocess.check_call(cmd)
    except subprocess.CalledProcessError as e:
        print(f"❌ Publish failed with exit code {e.returncode}")
        sys.exit(1)

if __name__ == "__main__":
    main()
