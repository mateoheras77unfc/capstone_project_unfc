"""
app/api/v1/endpoints/nova_insight.py
──────────────────────────────────────
Generate a 2-3 sentence plain-English forecast insight via Amazon Bedrock
Nova 2 Lite for any asset (stocks and crypto).

Route
-----
POST /api/v1/nova/insight

Accepts forecast data (point forecast, bounds, dates) and an optional
sentiment label, then asks Nova to produce a short analyst note.
No web grounding is used — Nova interprets the numbers we provide.
"""

import logging
from typing import List, Optional

import boto3
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()


class NovaInsightRequest(BaseModel):
    symbol: str
    point_forecast: List[float] = Field(..., min_length=1)
    lower_bound: List[float]
    upper_bound: List[float]
    dates: List[str]
    sentiment: Optional[str] = None  # "bullish" | "bearish" | "neutral" | None


class NovaInsightResponse(BaseModel):
    symbol: str
    insight: str


@router.post("/", response_model=NovaInsightResponse, summary="Generate Nova insight for any asset forecast")
async def nova_insight(request: NovaInsightRequest) -> NovaInsightResponse:
    """
    Generate a 2-3 sentence plain-English forecast insight using Amazon Bedrock
    Nova 2 Lite. Works for both stocks and crypto assets.

    Nova interprets the forecast numbers directly — no web grounding is used.
    Falls back to an empty insight if AWS credentials are not configured.
    """
    settings = get_settings()
    if not settings.AWS_ACCESS_KEY_ID or not settings.AWS_SECRET_ACCESS_KEY:
        raise HTTPException(status_code=503, detail="AWS credentials not configured")

    pts = request.point_forecast
    lbs = request.lower_bound
    ubs = request.upper_bound
    symbol = request.symbol.upper()
    asset_name = symbol.replace("-USD", "").replace("-", " ")

    current = pts[0]
    final = pts[-1]
    pct_change = ((final - current) / current) * 100
    direction = "increase" if pct_change >= 0 else "decrease"
    low_range = min(lbs)
    high_range = max(ubs)
    n_days = len(pts)
    sentiment = request.sentiment or "neutral"

    prompt = (
        f"You are a concise financial analyst. Based on the following {n_days}-day price forecast "
        f"for {asset_name} ({symbol}), write exactly 2-3 sentences of plain-English insight "
        f"for a retail investor. Be direct and specific. Do not use bullet points.\n\n"
        f"Forecast data:\n"
        f"- Day 1 price: ${current:,.2f}\n"
        f"- Day {n_days} price: ${final:,.2f} ({pct_change:+.2f}% {direction})\n"
        f"- {n_days}-day range: ${low_range:,.2f} – ${high_range:,.2f} (95% confidence interval)\n"
        f"- Current market sentiment: {sentiment}\n\n"
        f"Write the insight now:"
    )

    try:
        client = boto3.client(
            "bedrock-runtime",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )
        response = client.converse(
            modelId="us.amazon.nova-2-lite-v1:0",
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 150, "temperature": 0.4},
        )
        for block in response.get("output", {}).get("message", {}).get("content", []):
            if "text" in block:
                insight = block["text"].strip()
                logger.info("Nova insight generated for %s (%d chars)", symbol, len(insight))
                return NovaInsightResponse(symbol=symbol, insight=insight)
    except Exception as exc:
        logger.warning("Nova insight failed for %s: %s", symbol, exc)
        raise HTTPException(status_code=503, detail=f"Nova insight generation failed: {exc}") from exc

    return NovaInsightResponse(symbol=symbol, insight="")
