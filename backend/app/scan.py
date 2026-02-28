from __future__ import annotations
import io
import json
import uuid
from pathlib import Path
from typing import List, Dict

import httpx
import pandas as pd
from ta.trend import SMAIndicator, MACD
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange
from tenacity import retry, stop_after_attempt, wait_exponential

from .scoring import score_candidate, compute_plan

DATA_DIR = Path(__file__).resolve().parent / "data"
NASDAQ100_PATH = DATA_DIR / "nasdaq100.json"


def load_nasdaq100() -> List[str]:
    if NASDAQ100_PATH.exists():
        return json.loads(NASDAQ100_PATH.read_text())
    # fallback (if file missing) to your original sample to avoid hard crash
    return [
        "AAPL","MSFT","NVDA","AMZN","GOOGL","META","TSLA","AMD","INTC","AVGO",
        "NFLX","COST","PEP","ADBE","CSCO","QCOM","TXN","INTU","AMAT","PYPL",
    ]


NASDAQ_100 = load_nasdaq100()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=6))
def fetch_ohlcv(ticker: str) -> pd.DataFrame:
    """
    Fetch daily OHLCV from Stooq (no key). Tickers are like AAPL -> aapl.us
    """
    symbol = f"{ticker.lower()}.us"
    url = f"https://stooq.com/q/d/l/?s={symbol}&i=d"

    r = httpx.get(url, timeout=20)
    r.raise_for_status()

    df = pd.read_csv(io.StringIO(r.text))
    if df is None or df.empty:
        return pd.DataFrame()

    # Stooq columns: Date, Open, High, Low, Close, Volume
    df.columns = [c.lower() for c in df.columns]
    df = df.rename(columns={"date": "date"})
    # Ensure numeric
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["close", "high", "low", "open"])
    return df

def compute_features(df: pd.DataFrame) -> Dict[str, float]:
    """
    Compute last-row indicators from df.
    Expects columns: open/high/low/close/volume
    """
    close = df["close"]
    high = df["high"]
    low = df["low"]

    sma50 = SMAIndicator(close, window=50).sma_indicator()
    sma200 = SMAIndicator(close, window=200).sma_indicator()

    rsi14 = RSIIndicator(close, window=14).rsi()

    macd = MACD(close, window_slow=26, window_fast=12, window_sign=9)
    macd_hist = macd.macd_diff()

    atr14 = AverageTrueRange(high, low, close, window=14).average_true_range()

    # volume ratio: last volume / avg 20
    vol20 = df["volume"].rolling(20).mean()
    vol_ratio = (df["volume"].iloc[-1] / vol20.iloc[-1]) if vol20.iloc[-1] and vol20.iloc[-1] > 0 else 1.0

    last_close = float(close.iloc[-1])
    last_atr = float(atr14.iloc[-1]) if not pd.isna(atr14.iloc[-1]) else 0.0
    atrp = (last_atr / last_close) if last_close > 0 else 0.0

    return {
        "close": round(last_close, 4),
        "sma50": float(sma50.iloc[-1]) if not pd.isna(sma50.iloc[-1]) else float("nan"),
        "sma200": float(sma200.iloc[-1]) if not pd.isna(sma200.iloc[-1]) else float("nan"),
        "rsi14": float(rsi14.iloc[-1]) if not pd.isna(rsi14.iloc[-1]) else float("nan"),
        "macd_hist": float(macd_hist.iloc[-1]) if not pd.isna(macd_hist.iloc[-1]) else float("nan"),
        "atr14": last_atr,
        "vol_ratio": float(vol_ratio),
        "atrp": float(atrp),
    }

def scan_universe(universe: str, risk_dollars: float, top_n: int = 3) -> dict:
    tickers = NASDAQ_100 if universe == "nasdaq100" else NASDAQ_100

    rows = []
    for t in tickers:
        df = fetch_ohlcv(t)
        if df.empty or len(df) < 60:
            continue
        feat = compute_features(df)

        # basic trend filter to reduce noise
        if not (feat["close"] > feat["sma50"] and feat["sma50"] > feat["sma200"]):
            continue

        score, breakdown = score_candidate(feat)
        plan = compute_plan(price=feat["close"], atr=feat["atr14"], risk_dollars=risk_dollars)

        rows.append({
            "ticker": t,
            "score": score,
            "breakdown": breakdown,
            "indicators": {
                "close": round(feat["close"], 2),
                "sma50": round(feat["sma50"], 2),
                "sma200": round(feat["sma200"], 2),
                "rsi14": round(feat["rsi14"], 2),
                "macd_hist": round(feat["macd_hist"], 4),
                "atr14": round(feat["atr14"], 2),
                "vol_ratio": round(feat["vol_ratio"], 2),
                "atrp": round(feat["atrp"], 4),
            },
            "plan": plan
        })

    if not rows:
        return {
            "run_id": str(uuid.uuid4()),
            "top": [],
            "top10": [],
            "universe_size": len(tickers),
            "scanned": 0,
            "error": "No data fetched (data provider blocked or rate-limited).",
        }

    rows.sort(key=lambda x: x["score"], reverse=True)
    run_id = str(uuid.uuid4())
    return {
        "run_id": run_id,
        "top": rows[:max(1, top_n)],
        "top10": rows[:10],
        "universe_size": len(tickers),
        "scanned": len(rows),
    }
