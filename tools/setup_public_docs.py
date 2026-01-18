#!/usr/bin/env python3
import subprocess
import json
import urllib.request
import urllib.error
import sys
import re

def get_git_remote_url():
    try:
        url = subprocess.check_output(["git", "remote", "get-url", "origin"]).decode().strip()
        return url
    except subprocess.CalledProcessError:
        return None

def extract_credentials(url):
    # Match pattern: https://oauth2:TOKEN@gitlab.com/... or https://USER:TOKEN@gitlab.com/...
    # Focusing on the token part
    match = re.search(r"https://[^:]+:([^@]+)@gitlab.com", url)
    if match:
        return match.group(1)
    return None

def create_gitlab_repo(token, repo_name="tradebot-docs"):
    url = "https://gitlab.com/api/v4/projects"
    data = {
        "name": repo_name,
        "visibility": "public",
        "description": "Public documentation for Tradebot SCI",
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
            print(f"✅ Repository created successfully: {result['web_url']}")
            return result['http_url_to_repo']
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        if e.code == 400 and "marketing name already taken" in body.lower():
             # Try getting the existing repo if it failed because it exists
            print(f"⚠️  Repo '{repo_name}' might already exist. Checking...")
            return get_existing_repo(token, repo_name)
        elif e.code == 400 and "has already been taken" in body.lower():
             print(f"⚠️  Repo '{repo_name}' already exists. Attempting to use it...")
             return get_existing_repo(token, repo_name)
            
        print(f"❌ Failed to create repository: {e.code} - {body}")
        return None

def get_existing_repo(token, repo_name):
    # List projects and filter
    url = f"https://gitlab.com/api/v4/projects?search={repo_name}&owned=true"
    req = urllib.request.Request(
        url,
        headers={"PRIVATE-TOKEN": token}
    )
    try:
        with urllib.request.urlopen(req) as response:
            projects = json.loads(response.read().decode())
            for p in projects:
                if p['name'] == repo_name:
                    return p['http_url_to_repo']
            return None
    except Exception as e:
        print(f"❌ Failed to check existing repos: {e}")
        return None

def main():
    print("🔍 Inspecting git configuration...")
    remote_url = get_git_remote_url()
    if not remote_url:
        print("❌ Could not find git remote URL.")
        sys.exit(1)

    print("🔑 Extracting credentials...")
    token = extract_credentials(remote_url)
    if not token:
        print("❌ Could not find API token in git remote URL.")
        print("   Please ensure you cloned with a PAT (Personal Access Token).")
        sys.exit(1)

    print("🚀 Connecting to GitLab API...")
    target_repo_url = create_gitlab_repo(token)
    
    if not target_repo_url:
        print("❌ Could not get a target repository URL.")
        sys.exit(1)
        
    # Inject credentials into the new URL for the push
    # Format: https://oauth2:TOKEN@gitlab.com/user/repo.git
    if "https://" in target_repo_url and "@" not in target_repo_url:
        authenticated_url = target_repo_url.replace("https://", f"https://oauth2:{token}@", 1)
    else:
        authenticated_url = target_repo_url

    print(f"📦 Publishing 'Documentation' to {target_repo_url}...")
    
    # Run the bash script
    cmd = ["./scripts/publish_folder.sh", "Documentation", authenticated_url, "main"]
    subprocess.check_call(cmd)

if __name__ == "__main__":
    main()
