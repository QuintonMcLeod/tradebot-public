import urllib.request
import xml.etree.ElementTree as ET
import json
import os
import re
from datetime import datetime
import logging

logger = logging.getLogger("sys.news_scraper")

class RSSNewsScraper:
    """
    Zero-API RSS news parser tailored for Forex/Crypto/Indices.
    Pulls data from public non-authenticated feeds (ForexLive, Investing, Reddit)
    to provide essential macro-economic context to the Seasoned Trader Sentinel AI.
    """
    
    FEEDS = {
        "forex": "https://www.forexlive.com/feed/news",
        "crypto": "https://cointelegraph.com/rss",
        "reddit_daytrading": "https://www.reddit.com/r/Daytrading/new/.rss?sort=new",
        "reddit_forex": "https://www.reddit.com/r/Forex/new/.rss?sort=new"
    }

    def __init__(self, cache_dir: str = "/tmp/tradebot_ai_cache"):
        self.cache_dir = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)
        self.cache_file = os.path.join(self.cache_dir, "rss_cache.json")
        self._cache = self._load_cache()

    def _load_cache(self) -> dict:
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_cache(self):
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self._cache, f)
        except Exception as e:
            logger.error(f"[RSS Scraper] Failed to save cache: {e}")

    def fetch_feed(self, url: str) -> list:
        try:
            req = urllib.request.Request(
                url, 
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0'}
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                content = response.read()
            
            root = ET.fromstring(content)
            items = []
            
            # Atom vs RSS handling
            if 'http://www.w3.org/2005/Atom' in root.tag:
                namespace = {'atom': 'http://www.w3.org/2005/Atom'}
                for entry in root.findall('atom:entry', namespace)[:10]:
                    title = entry.find('atom:title', namespace)
                    content_node = entry.find('atom:content', namespace) or entry.find('atom:summary', namespace)
                    if title is not None:
                        clean_content = re.sub('<[^<]+>', '', content_node.text) if content_node is not None and content_node.text else ""
                        items.append(f"{title.text} - {clean_content[:200]}")
            else:
                for item in root.findall('.//item')[:10]:
                    title = item.find('title')
                    desc = item.find('description')
                    if title is not None:
                        clean_desc = re.sub('<[^<]+>', '', desc.text) if desc is not None and desc.text else ""
                        items.append(f"{title.text} - {clean_desc[:200]}")
            
            return items
        except Exception as e:
            logger.error(f"[RSS Scraper] Error fetching {url}: {e}")
            return []

    def get_latest_news_context(self) -> str:
        """
        Polls all predefined feeds and aggregates the top headlines into a dense
        context string for the LLM. Caches the result to avoid spamming endpoints.
        """
        now = datetime.now()
        last_fetch = self._cache.get("last_fetch", 0)
        
        # 15-minute soft cache to prevent IP bans from Reddit/ForexLive
        if (now.timestamp() - last_fetch) < 900 and "context" in self._cache:
            return self._cache["context"]

        logger.info("[RSS Scraper] Fetching fresh global news...")
        agg_context = []
        for category, url in self.FEEDS.items():
            headlines = self.fetch_feed(url)
            if headlines:
                agg_context.append(f"--- {category.upper()} UPDATE ---")
                agg_context.extend([f"• {h}" for h in headlines[:5]])
        
        context_str = "\n".join(agg_context)
        if not context_str:
            context_str = "No recent macroeconomic or trading news available."

        self._cache["last_fetch"] = now.timestamp()
        self._cache["context"] = context_str
        self._save_cache()

        return context_str

if __name__ == '__main__':
    scraper = RSSNewsScraper()
    print(scraper.get_latest_news_context())
