# backend/app/chat_routes.py
#
# Add to backend/app/main.py:
#   from app.chat_routes import router as chat_router
#   app.include_router(chat_router)
#
# FREE LLM options (pick one):
#   A) Groq (free tier, very fast) → https://console.groq.com → set GROQ_API_KEY
#   B) Google Gemini (free tier)   → https://aistudio.google.com → set GEMINI_API_KEY
#   C) OpenRouter free models      → https://openrouter.ai → set OPENROUTER_API_KEY
#
# Install: pip install fastapi httpx python-dotenv

import os
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api")

# ── System prompt: Canadian investment educator ───────────────────────────────
SYSTEM_PROMPT = """You are Foxy, a friendly and expert financial educator specialized in Canadian banking and investment markets. You help users understand:

- Canadian tax-advantaged accounts: TFSA, RRSP, RESP, FHSA, RDSP
- Canadian stock market: TSX (Toronto Stock Exchange), TSX Venture Exchange
- Canadian ETFs, mutual funds, GICs, bonds, REITs
- Canadian banks: Big Six (RBC, TD, BMO, Scotiabank, CIBC, National Bank)
- CDIC deposit insurance, CIPF investor protection
- Canadian tax rules: capital gains, dividend tax credits, ACB tracking
- Robo-advisors in Canada: Wealthsimple, Questrade, CI Direct
- Portfolio optimization concepts: Markowitz, Sharpe ratio, diversification
- Investment forecasting concepts: EWM, time series, risk metrics

Rules:
- Always clarify you are for educational purposes only, not licensed financial advice
- Be encouraging, clear, and avoid unexplained jargon
- Use Canadian context (CAD, CRA rules, Canadian brokers)
- For complex personal situations, recommend a licensed advisor (IIROC/MFDA registered)
- Respond in the same language the user writes in (English or Spanish)
- Keep answers concise but complete — aim for 3-5 sentences unless more detail is needed"""


# ── Request / Response schemas ────────────────────────────────────────────────
class ChatMessage(BaseModel):
    role: str   # "user" | "assistant"
    content: str

class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


# ── ─────────────────────────────────────────────────────────────────────────
#    OPTION A: GROQ (recommended — free, fast, llama3)
# ── ─────────────────────────────────────────────────────────────────────────
@router.post("/chat")
async def chat(req: ChatRequest):
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY not set")

    messages = [
        {"role": m.role, "content": m.content}
        for m in req.history[-8:]  # keep last 8 turns
    ]
    messages.append({"role": "user", "content": req.message})

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "llama3-8b-8192",   # free on Groq
                "max_tokens": 600,
                "temperature": 0.65,
                "system": SYSTEM_PROMPT,
                "messages": messages,
            },
        )

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"LLM error: {resp.text}")

    reply = resp.json()["choices"][0]["message"]["content"]
    return {"reply": reply}


# ── ─────────────────────────────────────────────────────────────────────────
#    OPTION B: Google Gemini (uncomment to use instead of Groq)
# ── ─────────────────────────────────────────────────────────────────────────
# @router.post("/chat")
# async def chat(req: ChatRequest):
#     api_key = os.getenv("GEMINI_API_KEY")
#     if not api_key:
#         raise HTTPException(status_code=500, detail="GEMINI_API_KEY not set")
#
#     # Build Gemini-style history
#     contents = []
#     for m in req.history[-8:]:
#         role = "user" if m.role == "user" else "model"
#         contents.append({"role": role, "parts": [{"text": m.content}]})
#     contents.append({"role": "user", "parts": [{"text": req.message}]})
#
#     async with httpx.AsyncClient(timeout=30) as client:
#         resp = await client.post(
#             f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}",
#             json={
#                 "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
#                 "contents": contents,
#                 "generationConfig": {"maxOutputTokens": 600, "temperature": 0.65},
#             },
#         )
#
#     if resp.status_code != 200:
#         raise HTTPException(status_code=502, detail=f"LLM error: {resp.text}")
#
#     reply = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
#     return {"reply": reply}


# ── ─────────────────────────────────────────────────────────────────────────
#    OPTION C: OpenRouter (access many free models)
# ── ─────────────────────────────────────────────────────────────────────────
# @router.post("/chat")
# async def chat(req: ChatRequest):
#     api_key = os.getenv("OPENROUTER_API_KEY")
#     if not api_key:
#         raise HTTPException(status_code=500, detail="OPENROUTER_API_KEY not set")
#
#     messages = [{"role": m.role, "content": m.content} for m in req.history[-8:]]
#     messages.append({"role": "user", "content": req.message})
#
#     async with httpx.AsyncClient(timeout=30) as client:
#         resp = await client.post(
#             "https://openrouter.ai/api/v1/chat/completions",
#             headers={
#                 "Authorization": f"Bearer {api_key}",
#                 "Content-Type": "application/json",
#             },
#             json={
#                 "model": "mistralai/mistral-7b-instruct:free",  # free tier
#                 "max_tokens": 600,
#                 "messages": [{"role": "system", "content": SYSTEM_PROMPT}, *messages],
#             },
#         )
#
#     if resp.status_code != 200:
#         raise HTTPException(status_code=502, detail=f"LLM error: {resp.text}")
#
#     reply = resp.json()["choices"][0]["message"]["content"]
#     return {"reply": reply}