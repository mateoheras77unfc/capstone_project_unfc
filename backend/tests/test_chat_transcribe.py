"""
tests/test_chat_transcribe.py
──────────────────────────────
Tests for the POST /chat/transcribe endpoint, focusing on the upload-size
and content-type guardrails added to prevent memory abuse and unnecessary
upstream calls to Groq Whisper.
"""

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.v1.endpoints.chat import (
    ALLOWED_AUDIO_CONTENT_TYPES,
    MAX_AUDIO_BYTES,
)


# ── Shared fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def mock_groq_transcribe():
    """
    Patch ``httpx.AsyncClient`` so the transcription endpoint never makes a
    real network call to Groq.  Yields the mocked ``post`` coroutine so tests
    can inspect or override it if needed.

    Yields:
        AsyncMock: The mocked ``client.post`` coroutine.
    """
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"text": "test transcript"}

    mock_client_instance = AsyncMock()
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=False)
    mock_client_instance.post = AsyncMock(return_value=mock_response)

    with patch("app.api.v1.endpoints.chat.os.getenv", return_value="fake-api-key"), \
         patch("httpx.AsyncClient", return_value=mock_client_instance):
        yield mock_client_instance.post


# ── Rejection tests ───────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_transcribe_rejects_invalid_content_type(app_client):
    """
    POST /chat/transcribe with an unsupported MIME type must return 400
    before any file data is read or sent to Groq.
    """
    payload = io.BytesIO(b"fake audio data")
    resp = await app_client.post(
        "/api/v1/chat/transcribe",
        files={"file": ("clip.mp3", payload, "application/octet-stream")},
    )
    assert resp.status_code == 400
    assert "Unsupported content type" in resp.json()["detail"]


@pytest.mark.anyio
async def test_transcribe_rejects_oversized_upload(app_client):
    """
    POST /chat/transcribe with a payload exceeding MAX_AUDIO_BYTES must
    return 413, not 500 or a silent OOM.
    """
    # Build a byte stream slightly larger than the limit.
    oversized = io.BytesIO(b"x" * (MAX_AUDIO_BYTES + 1))
    resp = await app_client.post(
        "/api/v1/chat/transcribe",
        files={"file": ("big.webm", oversized, "audio/webm")},
    )
    assert resp.status_code == 413
    assert "maximum allowed size" in resp.json()["detail"]


@pytest.mark.anyio
async def test_transcribe_rejects_content_type_with_codec_suffix(app_client):
    """
    A content_type like "application/x-shockwave-flash; codecs=opus" must
    still be rejected even though it carries a codec parameter.
    """
    payload = io.BytesIO(b"fake audio data")
    resp = await app_client.post(
        "/api/v1/chat/transcribe",
        files={
            "file": (
                "clip.webm",
                payload,
                "application/x-shockwave-flash; codecs=opus",
            )
        },
    )
    assert resp.status_code == 400


# ── Acceptance tests ──────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_transcribe_accepts_allowed_types_and_calls_groq(
    app_client, mock_groq_transcribe
):
    """
    POST /chat/transcribe with a valid content_type and payload within
    the size limit must forward the audio to Groq and return the transcript.
    """
    payload = io.BytesIO(b"tiny audio bytes")
    resp = await app_client.post(
        "/api/v1/chat/transcribe",
        files={"file": ("rec.webm", payload, "audio/webm")},
    )

    assert resp.status_code == 200
    assert resp.json() == {"transcript": "test transcript"}


@pytest.mark.anyio
async def test_transcribe_accepts_codec_suffixed_allowed_type(
    app_client, mock_groq_transcribe
):
    """
    "audio/webm; codecs=opus" is a real browser-emitted content_type.
    The endpoint must strip the codec parameter and accept it as audio/webm.
    """
    payload = io.BytesIO(b"tiny audio bytes")
    resp = await app_client.post(
        "/api/v1/chat/transcribe",
        files={"file": ("rec.webm", payload, "audio/webm; codecs=opus")},
    )

    assert resp.status_code == 200


# ── Sanity checks ─────────────────────────────────────────────────────────────


def test_allowed_audio_content_types_is_nonempty():
    """
    Sanity-check that the allowlist was not accidentally left empty.
    """
    assert len(ALLOWED_AUDIO_CONTENT_TYPES) > 0


def test_max_audio_bytes_is_positive():
    """
    Sanity-check that the size constant is a positive integer.
    """
    assert isinstance(MAX_AUDIO_BYTES, int)
    assert MAX_AUDIO_BYTES > 0
