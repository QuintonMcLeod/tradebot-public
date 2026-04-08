import logging
import requests
import threading
import time
import uuid

logger = logging.getLogger(__name__)

class TradovateClient:
    """REST wrapper for Tradovate futures API (Apex Trader Funding prop firm)."""

    def __init__(self, username, password, app_id, is_live=False):
        self.username = username
        self.password = password
        self.app_id = app_id
        
        # Apex Evaluation / Combine lives on the Demo endpoint. 
        # Only funded live accounts use the Live endpoint.
        self.base_url = "https://live.tradovateapi.com/v1" if is_live else "https://demo.tradovateapi.com/v1"
        self.device_id = str(uuid.uuid4())
        
        self.access_token = None
        self.token_expiry_time = 0
        
        self._refresh_lock = threading.Lock()
        
        self._authenticate()
        
        # Start proactive background token refresh loop
        self._refresh_thread_stop = threading.Event()
        self._refresh_thread = threading.Thread(target=self._token_refresh_loop, daemon=True, name="TradovateTokenRefresh")
        self._refresh_thread.start()

    def close(self):
        self._refresh_thread_stop.set()

    def _token_refresh_loop(self):
        """Background daemon that automatically requests a new Tradovate token before expiry."""
        while not self._refresh_thread_stop.is_set():
            # Wait 45 minutes between background authentications
            for _ in range(45 * 60):
                if self._refresh_thread_stop.is_set():
                    return
                time.sleep(1)
                
            logger.info("[TRADOVATE] Initiating proactive background token refresh...")
            # Forcing expiration to bypass cache in _authenticate
            self.token_expiry_time = 0
            self._authenticate()

    def is_authenticated(self):
        return self.access_token is not None

    def _authenticate(self):
        with self._refresh_lock:
            # Avoid re-auth if token is still good
            if self.access_token and time.time() < self.token_expiry_time - 300:
                return

            payload = {
                "name": self.username,
                "password": self.password,
                "appId": self.app_id,
                "appVersion": "1.0.0",
                "deviceId": self.device_id,
                "cid": 1,
                "sec": ""
            }
            
            logger.info(f"[TRADOVATE] Authenticating with URL: {self.base_url}/auth/accesstokenrequest")
            try:
                resp = requests.post(f"{self.base_url}/auth/accesstokenrequest", json=payload, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    self.access_token = data.get("accessToken")
                    # Tokens expire after varied times, proactively refreshing every hour avoids TTL panic.
                    self.token_expiry_time = time.time() + 3600
                    logger.info("[TRADOVATE] Received new Access Token successfully.")
                else:
                    logger.error(f"[TRADOVATE] Auth failed: {resp.status_code} - {resp.text}")
                    self.access_token = None
            except Exception as e:
                logger.error(f"[TRADOVATE] Error connecting to auth server: {e}")
                self.access_token = None

    def _get_headers(self):
        if time.time() > self.token_expiry_time - 300:
            self._authenticate()
        
        if not self.access_token:
            return {}
        return {"Authorization": f"Bearer {self.access_token}", "Accept": "application/json", "Content-Type": "application/json"}

    def get(self, endpoint, params=None):
        headers = self._get_headers()
        try:
            r = requests.get(f"{self.base_url}/{endpoint}", headers=headers, params=params, timeout=10)
            if r.status_code == 401:
                logger.warning("[TRADOVATE] Token expired gracefully during GET. Re-authenticating...")
                self.token_expiry_time = 0
                headers = self._get_headers()
                r = requests.get(f"{self.base_url}/{endpoint}", headers=headers, params=params, timeout=10)
            return r.status_code, r.json() if r.content else {}
        except Exception as e:
            logger.error(f"[TRADOVATE] GET {endpoint} failed: {e}")
            return 500, {}

    def post(self, endpoint, payload):
        headers = self._get_headers()
        try:
            r = requests.post(f"{self.base_url}/{endpoint}", headers=headers, json=payload, timeout=10)
            if r.status_code == 401:
                logger.warning("[TRADOVATE] Token expired gracefully during POST. Re-authenticating...")
                self.token_expiry_time = 0
                headers = self._get_headers()
                r = requests.post(f"{self.base_url}/{endpoint}", headers=headers, json=payload, timeout=10)
            return r.status_code, r.json() if r.content else {}
        except Exception as e:
            logger.error(f"[TRADOVATE] POST {endpoint} failed: {e}")
            return 500, {}
