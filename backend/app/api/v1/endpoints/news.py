"""
app/api/v1/endpoints/news.py
────────────────────────────
Real-time financial news endpoint powered by Amazon Bedrock Nova 2 Lite
with web grounding.

Overview
--------
Returns the single most important financial news article for a given asset
symbol (stock or crypto), including a sentiment classification (bullish /
bearish / neutral), a 2-3 sentence summary, the publication source, and a
verified URL sourced directly from the web via Bedrock's grounding system.

How it works
------------
1. A natural-language prompt is sent to ``amazon.nova-2-lite-v1:0`` via the
   Bedrock Converse API with ``nova_grounding`` enabled as a system tool.
2. Nova performs a real web search, retrieves live articles, and generates a
   grounded response with citations.
3. The endpoint extracts the first citation URL (a real, verified link) from
   the ``citationsContent`` blocks in the response.
4. The natural-language response is parsed to extract:
   - **Title** — the article headline (stripped of markdown artifacts).
   - **Summary** — 2-3 sentence overview of the key points.
   - **Sentiment** — inferred from keywords + Nova's explicit mention
     (bullish / bearish / neutral).
   - **Source** — publication name detected from the response text or
     derived from the citation URL domain as fallback.

Why Nova 2 Lite + grounding instead of Nova Micro
--------------------------------------------------
Nova Micro is a lightweight completion model that cannot search the web —
it generates plausible-sounding but hallucinated URLs from training data.
Nova 2 Lite with ``nova_grounding`` performs an actual web search, so every
URL in the response points to a real, live article. This ensures the
"Read more →" link on the frontend always resolves correctly.

Route
-----
GET /api/v1/news/{symbol}

Returns
-------
NewsResponse
    symbol : str
    news   : list[NewsItem]   ← always a single-item list (top article only)

Future Research
---------------
- Store daily Nova sentiment scores in the database to build a historical
  sentiment time series, enabling its use as a proper ``hist_exog`` training
  feature in N-HiTS without relying on inference-time patching.
- Expand to return the top-3 articles (requires prompt restructuring to avoid
  suppressing grounding when a JSON output format is requested).
- Evaluate sentiment accuracy against labelled financial news benchmarks
  (e.g., FinBERT on FiQA or Headline datasets).
"""
from __future__ import annotations

import logging

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()


class NewsItem(BaseModel):
    title: str
    summary: str
    sentiment: str        # "bullish" | "bearish" | "neutral"
    source: str
    url: str


class NewsResponse(BaseModel):
    symbol: str
    news: list[NewsItem]


def _get_bedrock_client():
    settings = get_settings()
    return boto3.client(
        "bedrock-runtime",
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    )


PROMPT_TEMPLATE = (
    "Search the web for the single most important financial news article about {symbol} ({asset_name}) "
    "published in the last 7 days. "
    "Tell me: the article headline, a 2-3 sentence summary of the key points, "
    "the publication name, and whether the news is bullish, bearish, or neutral for the stock."
)


def _extract_first_url(response: dict) -> str:
    """Return the first real URL from Bedrock grounding citations."""
    for block in response.get("output", {}).get("message", {}).get("content", []):
        for citation in block.get("citationsContent", {}).get("citations", []):
            url = citation.get("location", {}).get("web", {}).get("url", "")
            if url:
                return url
    return ""


def _extract_text_blocks(response: dict) -> str:
    """Concatenate all text blocks from the Converse API response."""
    parts = []
    for block in response.get("output", {}).get("message", {}).get("content", []):
        if "text" in block:
            parts.append(block["text"])
    return " ".join(parts).strip()


def _infer_sentiment(text: str) -> str:
    text_lower = text.lower()
    bullish_words = ["bullish", "surge", "gain", "beat", "strong", "growth", "rally", "up", "positive", "rose", "rises"]
    bearish_words = ["bearish", "drop", "fall", "miss", "weak", "decline", "down", "negative", "fell", "falls", "loss"]
    bull_score = sum(1 for w in bullish_words if w in text_lower)
    bear_score = sum(1 for w in bearish_words if w in text_lower)
    if bull_score > bear_score:
        return "bullish"
    if bear_score > bull_score:
        return "bearish"
    return "neutral"


def _parse_response(text: str, symbol: str) -> dict:
    """Extract title, summary, source, sentiment from Nova's natural language response."""
    import re

    clean = re.sub(r"#{1,6}\s*", "", text)   # strip markdown headings
    clean = clean.replace("**", "").replace("*", "").strip()

    # Try to extract actual headline after "titled" or "headline:"
    titled_match = re.search(r'(?:titled|headline[:\s]+)\s+["\u201c\u2018]?([^\n"]{15,120})', clean, re.IGNORECASE)
    if titled_match:
        title = titled_match.group(1).strip().rstrip(".,\u201d\u2019")[:120]
    else:
        # Fallback: first non-preamble sentence
        preamble_re = re.compile(r"^(the most|here is|below is|one of|a recent|according|this)", re.IGNORECASE)
        sentences = [s.strip() for s in clean.replace("\n", " ").split(".") if len(s.strip()) > 20]
        title = next((s[:120] for s in sentences if not preamble_re.match(s)), f"Latest news on {symbol}")

    # Summary: bullet points or first 3 sentences of the body
    bullet_matches = re.findall(r"[-•]\s+(.+?)(?=\n[-•]|\Z)", clean, re.DOTALL)
    if bullet_matches:
        summary = " ".join(b.strip() for b in bullet_matches[:3])
    else:
        body_sentences = [s.strip() for s in clean.replace("\n", " ").split(".") if len(s.strip()) > 30]
        summary = ". ".join(body_sentences[1:4]) + "."

    # Source: scan for known publication names
    known_sources = [
        "Reuters", "Bloomberg", "CNBC", "Wall Street Journal", "WSJ",
        "Financial Times", "MarketWatch", "Motley Fool", "Barron's",
        "Seeking Alpha", "Yahoo Finance", "Forbes", "Business Insider",
        "StockTwits", "Investopedia", "The Verge", "TechCrunch",
        "CoinDesk", "CoinTelegraph", "Benzinga",
    ]
    source = ""
    for s in known_sources:
        if s.lower() in clean.lower():
            source = s
            break

    sentiment = _infer_sentiment(text)
    if "bullish" in text.lower():
        sentiment = "bullish"
    elif "bearish" in text.lower():
        sentiment = "bearish"

    return {"title": title, "summary": summary, "source": source, "sentiment": sentiment}


def _source_from_url(url: str) -> str:
    """Extract a readable source name from a URL domain."""
    import re
    if not url:
        return ""
    match = re.search(r"https?://(?:www\.)?([^/]+)", url)
    if not match:
        return ""
    domain = match.group(1)
    # Remove TLD to get readable name
    name = domain.rsplit(".", 1)[0].replace("-", " ").replace(".", " ")
    return name.title()


@router.get("/{symbol}", response_model=NewsResponse)
async def get_news(symbol: str):
    settings = get_settings()

    if not settings.AWS_ACCESS_KEY_ID or not settings.AWS_SECRET_ACCESS_KEY:
        raise HTTPException(status_code=503, detail="AWS credentials not configured")

    asset_name = symbol.replace("-USD", "").replace("-", " ")
    prompt = PROMPT_TEMPLATE.format(symbol=symbol, asset_name=asset_name)

    try:
        client = _get_bedrock_client()
        response = client.converse(
            modelId="us.amazon.nova-2-lite-v1:0",
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 512, "temperature": 0.2},
            toolConfig={"tools": [{"systemTool": {"name": "nova_grounding"}}]},
        )

        text = _extract_text_blocks(response)
        url = _extract_first_url(response)

        if not text:
            raise ValueError("Empty response from Nova")

        parsed = _parse_response(text, symbol)
        if not parsed["source"] and url:
            parsed["source"] = _source_from_url(url)

        return NewsResponse(
            symbol=symbol,
            news=[NewsItem(url=url, **parsed)],
        )

    except (BotoCoreError, ClientError) as e:
        logger.error("Bedrock error for %s: %s", symbol, e)
        raise HTTPException(status_code=502, detail=f"AWS Bedrock error: {str(e)}")
    except Exception as e:
        logger.error("News fetch failed for %s: %s", symbol, e)
        raise HTTPException(status_code=500, detail=f"Failed to fetch news: {str(e)}")
