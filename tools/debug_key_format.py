
import os
import sys
from dotenv import load_dotenv

# Load form .env
env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
load_dotenv(env_path)

secret = os.environ.get("CCXT_SECRET", "")
print(f"Loaded Secret Length: {len(secret)}")
print(f"First 50 chars: {secret[:50]}")
print(f"Contains literal newline chars: {'\n' in secret}")
print(f"Contains escaped newline sequence '\\n': {'\\n' in secret}")

# Attempt to fix if it's double-escaped
if '\\n' in secret and not '\n' in secret:
    print("Detected escaped newlines. Fixing...")
    fixed_secret = secret.replace('\\n', '\n')
    print(f"Fixed secret has real newlines: {'\n' in fixed_secret}")
