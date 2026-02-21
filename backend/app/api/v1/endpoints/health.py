"""
app/api/v1/endpoints/health.py
───────────────────────────────
Detailed health-check endpoint.

GET /api/v1/health

Returns the status of each sub-system (env vars, Supabase connectivity,
yfinance reachability) so the team can diagnose "nothing happens" issues
without digging through logs.
"""

import logging

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()


class SubsystemStatus(BaseModel):
    ok: bool
    detail: str


class HealthResponse(BaseModel):
    status: str          # "ok" | "degraded" | "error"
    environment: SubsystemStatus
    supabase: SubsystemStatus
    yfinance: SubsystemStatus


@router.get("/", response_model=HealthResponse, summary="Detailed health check")
def health() -> HealthResponse:
    """
    Check the status of every sub-system the sync pipeline depends on.

    Useful for diagnosing ``POST /assets/sync/{symbol}`` failures:

    - **environment** — Are ``SUPABASE_URL`` and ``SUPABASE_KEY`` set?
    - **supabase**    — Can we reach Supabase and query the ``assets`` table?
    - **yfinance**    — Can we fetch a single row from Yahoo Finance?

    Returns:
        Aggregated status with per-subsystem detail strings.
    """
    results: dict[str, SubsystemStatus] = {}

    # ── 1. Environment variables ──────────────────────────────────────────
    try:
        from core.config import get_settings
        settings = get_settings()
        url = str(settings.supabase_url)
        results["environment"] = SubsystemStatus(
            ok=True,
            detail=f"SUPABASE_URL={url[:30]}… SUPABASE_KEY=***set***",
        )
    except Exception as exc:
        results["environment"] = SubsystemStatus(
            ok=False,
            detail=f"Settings validation failed — {exc}. "
                   "Add SUPABASE_URL and SUPABASE_KEY to backend/.env or the hosting environment.",
        )

    # ── 2. Supabase connectivity ──────────────────────────────────────────
    try:
        from core.database import get_supabase_client
        db = get_supabase_client()
        db.table("assets").select("id").limit(1).execute()
        results["supabase"] = SubsystemStatus(ok=True, detail="Connected — assets table reachable")
    except Exception as exc:
        results["supabase"] = SubsystemStatus(
            ok=False,
            detail=f"{type(exc).__name__}: {exc}. "
                   "Check SUPABASE_URL/SUPABASE_KEY and that 'supabase start' is running locally.",
        )

    # ── 3. yfinance reachability ──────────────────────────────────────────
    try:
        import yfinance as yf
        df = yf.Ticker("AAPL").history(period="1d", interval="1d")
        if df.empty:
            results["yfinance"] = SubsystemStatus(
                ok=False, detail="yfinance returned empty data for AAPL test query"
            )
        else:
            results["yfinance"] = SubsystemStatus(
                ok=True, detail="Yahoo Finance reachable — AAPL test query returned data"
            )
    except Exception as exc:
        results["yfinance"] = SubsystemStatus(
            ok=False,
            detail=f"{type(exc).__name__}: {exc}. Check network connectivity.",
        )

    # ── Aggregate ─────────────────────────────────────────────────────────
    all_ok = all(s.ok for s in results.values())
    any_ok = any(s.ok for s in results.values())
    overall = "ok" if all_ok else ("degraded" if any_ok else "error")

    return HealthResponse(
        status=overall,
        environment=results["environment"],
        supabase=results["supabase"],
        yfinance=results["yfinance"],
    )
