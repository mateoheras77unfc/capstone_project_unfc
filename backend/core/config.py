"""
core/config.py
──────────────
Centralised application settings via ``pydantic-settings``.

All configuration is driven by environment variables (or a ``.env`` file
in the ``backend/`` directory).  ``pydantic-settings`` validates types at
startup, so missing required values fail fast with a clear error message.

Usage
-----
    from core.config import get_settings

    settings = get_settings()
    print(settings.SUPABASE_URL)
"""

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve the backend/ directory so relative .env paths work from any cwd.
_BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables / ``.env`` file.

    Attributes:
        APP_TITLE:       Human-readable API name shown in OpenAPI docs.
        APP_VERSION:     Semantic version string.
        APP_DESCRIPTION: Short description shown in the OpenAPI UI.
        DEBUG:           Enable verbose logging and hot-reload.
        SUPABASE_URL:    Supabase project URL (required).
        SUPABASE_KEY:    Supabase anon or service-role key (required).
        FRONTEND_URL:    Optional deployed frontend origin for CORS.
    """

    model_config = SettingsConfigDict(
        env_file=str(_BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        # Extra env vars are ignored — don't raise on unexpected keys.
        extra="ignore",
    )

    # ── API metadata ──────────────────────────────────────────────────────
    APP_TITLE: str = "Investment Analytics API"
    APP_VERSION: str = "0.2.0"
    APP_DESCRIPTION: str = (
        "Backend for the Educational Investment Platform. "
        "Provides historical prices, data sync, and forecasting endpoints."
    )

    # ── Feature flags ─────────────────────────────────────────────────────
    DEBUG: bool = False

    # ── Supabase (required) ───────────────────────────────────────────────
    SUPABASE_URL: str = Field(..., description="Supabase project URL")
    SUPABASE_KEY: str = Field(..., description="Supabase anon or service-role key")

    # ── AWS Bedrock (Nova) ────────────────────────────────────────────────
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"

    # ── CORS ──────────────────────────────────────────────────────────────
    # Optional extra origin injected by the hosting environment.
    FRONTEND_URL: str = ""

    @property
    def CORS_ORIGINS(self) -> List[str]:
        """
        Build the full CORS allow-list.

        Hard-coded dev origins plus the optional ``FRONTEND_URL`` env var.

        Returns:
            List of allowed origin strings.
        """
        origins: List[str] = [
            "http://localhost:5173",   # Vite / React dev server
            "http://127.0.0.1:5173",
            "http://localhost:3000",   # alternate dev port
            "http://127.0.0.1:3000",
            "http://localhost:8501",   # Streamlit (legacy)
            "http://127.0.0.1:8501",
            "https://capstone-project-unfc-ashen.vercel.app",
            "https://capstone-project-unfc.vercel.app",
            "https://capstoneproject.swiftshift.digital",  # production
        ]
        if self.FRONTEND_URL:
            origins.append(self.FRONTEND_URL)
        return origins

    @field_validator("SUPABASE_URL")
    @classmethod
    def _must_not_be_empty(cls, v: str) -> str:
        """Raise if a required URL field is blank."""
        if not v:
            raise ValueError("SUPABASE_URL must not be empty")
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return a cached ``Settings`` singleton.

    The instance is created (and the ``.env`` file parsed) only once per
    process lifetime, courtesy of ``functools.lru_cache``.

    Returns:
        Settings: Validated application configuration.
    """
    return Settings()
