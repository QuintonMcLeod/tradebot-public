import logging
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import httpx

logger = logging.getLogger(__name__)

# Constants
RSS_URL = "https://investinglive.com/feed/news"
CACHE_TTL_SECONDS = 900  # 15 minutes

# Global Cache State
_news_cache: str | None = None
_last_fetch_time: float = 0.0

def get_latest_news(limit: int = 5) -> str:
    """
    Fetches the latest financial news headlines from an RSS feed.
    Results are cached for 15 minutes to prevent hammering the source.
    Returns a formatted string of headlines ready for AI prompt injection.
    """
    global _news_cache, _last_fetch_time
    
    now = time.time()
    
    # Return cache if valid
    if _news_cache and (now - _last_fetch_time) < CACHE_TTL_SECONDS:
        return _news_cache

    try:
        logger.debug(f"[RSS] Fetching fresh news from {RSS_URL}")
        # Use a realistic User-Agent to avoid basic blocks
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        with httpx.Client(timeout=10.0, headers=headers) as client:
            # -L flag equivalent (follow redirects)
            response = client.get(RSS_URL, follow_redirects=True)
            response.raise_for_status()
            
            # Parse XML
            root = ET.fromstring(response.text)
            
            headlines = []
            # Find all <item> tags (RSS 2.0 standard)
            for item in root.findall('.//item')[:limit]:
                title_elem = item.find('title')
                desc_elem = item.find('description')
                
                if title_elem is not None and title_elem.text:
                    title = title_elem.text.strip()
                    # Clean up CDATA and weird formatting if present
                    if title.startswith('<![CDATA['):
                        title = title[9:-3]
                        
                    headlines.append(f"- {title}")
            
            if headlines:
                _news_cache = "\n".join(headlines)
                _last_fetch_time = now
                logger.info(f"[RSS] Fetched and cached {len(headlines)} news headlines.")
                return _news_cache
            else:
                logger.warning("[RSS] Successfully fetched feed but found no <item> tags.")
                
    except Exception as e:
        logger.warning(f"[RSS] Failed to fetch news feed: {e}")
        
    # If fetch fails and we have an old cache, it's better to use stale news than no news.
    if _news_cache:
        logger.debug("[RSS] Using stale cache due to fetch failure.")
        return _news_cache
        
    return "No recent market news available."
