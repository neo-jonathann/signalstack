import os
import urllib.parse
import httpx
import pandas as pd


def _proxy_url() -> str | None:
    host = os.getenv("BRIGHTDATA_HOST")
    port = os.getenv("BRIGHTDATA_PORT")
    user = os.getenv("BRIGHTDATA_USERNAME")
    pw = os.getenv("BRIGHTDATA_PASSWORD")
    if not all([host, port, user, pw]):
        return None
    return f"http://{user}:{pw}@{host}:{port}"


def _yahoo_chart_url(ticker: str, range_: str = "6mo", interval: str = "1d") -> str:
    # Yahoo chart endpoint (public)
    return f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}?range={range_}&interval={interval}"


async def fetch_ohlcv_yahoo_via_proxy(
    ticker: str,
    range_: str = "6mo",
    interval: str = "1d",
) -> pd.DataFrame:
    proxy = _proxy_url()
    print("YAHOO PROXY:", "ON" if proxy else "OFF")
    if proxy:
        u = urllib.parse.urlparse(proxy)
        print("YAHOO PROXY HOST:", u.hostname, "PORT:", u.port, "USER:", u.username)
    url = _yahoo_chart_url(ticker, range_, interval)

    headers = {
        # A realistic UA helps; some hosts return garbage to default UAs
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120 Safari/537.36"
        ),
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "en-US,en;q=0.9",
    }

    proxies = {"http://": proxy, "https://": proxy} if proxy else None

    async with httpx.AsyncClient(
        timeout=30,
        proxies=proxies,
        verify=False,
        follow_redirects=True,
        headers=headers,
    ) as client:
        r = await client.get(url)

    ct = r.headers.get("content-type", "")
    if r.status_code != 200:
        raise RuntimeError(f"Yahoo chart failed {ticker}: HTTP {r.status_code} {ct}")

    data = r.json()
    chart = (data.get("chart") or {})
    err = chart.get("error")
    if err:
        raise RuntimeError(f"Yahoo chart error {ticker}: {err}")

    result = (chart.get("result") or [None])[0]
    if not result:
        return pd.DataFrame()

    ts = result.get("timestamp") or []
    ind = ((result.get("indicators") or {}).get("quote") or [None])[0] or {}

    if not ts:
        return pd.DataFrame()

    df = pd.DataFrame(
        {
            "date": pd.to_datetime(ts, unit="s", utc=True)
            .tz_convert("Asia/Singapore")
            .tz_localize(None),
            "open": ind.get("open"),
            "high": ind.get("high"),
            "low": ind.get("low"),
            "close": ind.get("close"),
            "volume": ind.get("volume"),
        }
    )
    df = df.dropna(subset=["open", "high", "low", "close"])
    return df
