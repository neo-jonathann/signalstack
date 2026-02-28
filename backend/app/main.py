from __future__ import annotations
import asyncio
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .models import ScanRequest, ScanResponse, Candidate, Headline, TradePlan
from .scan import scan_universe
from .brightdata import get_headlines_for_ticker
from .llm import explain_pick

app = FastAPI(title="SignalStack", version="0.1.0")

# For local dev; in production you can lock this down
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
def health():
    return {"ok": True}

@app.post("/api/scan", response_model=ScanResponse)
async def scan(req: ScanRequest):
    base = scan_universe(req.universe, req.risk_dollars, top_n=req.top_n)

    rows = base["top"]

    headlines_map = {}
    if req.include_headlines:
        tickers = [r["ticker"] for r in rows]
        results = await asyncio.gather(
            *[get_headlines_for_ticker(t, limit=3) for t in tickers],
            return_exceptions=True
        )
        for t, res in zip(tickers, results):
            if isinstance(res, Exception):
                headlines_map[t] = []
            else:
                headlines_map[t] = res

    candidates = []
    for row in rows:
        hl = headlines_map.get(row["ticker"], [])
        headlines = [Headline(**h) for h in hl]

        reason_bullets = []
        risk_note = None

        if req.include_reasoning:
            llm_payload = {
                "ticker": row["ticker"],
                "score": row["score"],
                "score_breakdown": row["breakdown"],
                "indicators": row["indicators"],
                "plan": row["plan"],
                "headlines": hl
            }
            explained = await explain_pick(llm_payload)
            reason_bullets = explained.get("bullets", [])[:3]
            risk_note = explained.get("risk", None)

        candidates.append(Candidate(
            ticker=row["ticker"],
            score=row["score"],
            score_breakdown=row["breakdown"],
            indicators=row["indicators"],
            plan=TradePlan(**row["plan"]),
            headlines=headlines,
            reasoning=None,
            reason_bullets=reason_bullets,
            risk_note=risk_note,
        ))

    return ScanResponse(
        run_id=base["run_id"],
        candidates=candidates,
        meta={
            "universe": req.universe,
            "universe_size": base["universe_size"],
            "scanned": base["scanned"],
            "include_headlines": req.include_headlines,
            "error": base.get("error"),
        }
    )

# ---- Serve frontend (built Vite) from /frontend/dist via Docker build ----
FRONTEND_DIST = os.getenv("FRONTEND_DIST", "/app/frontend/dist")

if os.path.isdir(FRONTEND_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        # Serve index.html for SPA routes
        index_path = os.path.join(FRONTEND_DIST, "index.html")
        return FileResponse(index_path)
