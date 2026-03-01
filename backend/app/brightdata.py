from __future__ import annotations
import os
import time
from typing import List, Dict
import httpx
from bs4 import BeautifulSoup

BRIGHTDATA_API_KEY = os.getenv("BRIGHTDATA_API_KEY", "")
BRIGHTDATA_SERP_ZONE = os.getenv("BRIGHTDATA_SERP_ZONE", "")

# simple in-memory cache: query -> (expiry, headlines)
_CACHE: Dict[str, tuple[float, List[dict]]] = {}

def _cache_get(key: str):
    v = _CACHE.get(key)
    if not v:
        return None
    exp, data = v
    if time.time() > exp:
        _CACHE.pop(key, None)
        return None
    return data

def _cache_set(key: str, data: List[dict], ttl_sec: int = 900):
    _CACHE[key] = (time.time() + ttl_sec, data)

async def fetch_serp_html(query: str) -> str:
    if not BRIGHTDATA_API_KEY or not BRIGHTDATA_SERP_ZONE:
        return ""

    payload = {
        "zone": BRIGHTDATA_SERP_ZONE,
        "url": f"https://www.google.com/search?q={query}",
        "format": "raw"
    }
    headers = {
        "Authorization": f"Bearer {BRIGHTDATA_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                "https://api.brightdata.com/request",
                json=payload,
                headers=headers,
            )
            r.raise_for_status()
            return r.text
    except Exception as e:
        print("BRIGHTDATA FAIL", query, repr(e))
        return ""

def parse_google_headlines(html: str, limit: int = 5) -> List[dict]:
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")

    # Google's HTML changes often; keep parsing forgiving.
    # Common heuristic: result blocks have <a> with <h3>
    results = []
    for a in soup.select("a"):
        h3 = a.find("h3")
        if not h3:
            continue
        title = h3.get_text(strip=True)
        href = a.get("href") or ""
        if not title or not href.startswith("http"):
            continue
        results.append({"title": title, "url": href})
        if len(results) >= limit:
            break
    return results

async def get_headlines_for_ticker(ticker: str, limit: int = 5) -> List[dict]:
    key = f"news:{ticker}:{limit}"
    cached = _cache_get(key)
    if cached is not None:
        return cached

    query = f"{ticker} stock news"
    html = await fetch_serp_html(query)
    headlines = parse_google_headlines(html, limit=limit)
    _cache_set(key, headlines, ttl_sec=900)
    return headlines
