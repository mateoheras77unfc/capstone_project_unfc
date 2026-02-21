"""
=============================================================================
APPLICATION CONFIGURATION - Centralised Settings
=============================================================================

Uses python-dotenv so values can be supplied via a root .env file or
real environment variables (e.g. on Render).

Usage
-----
from backend.core.config import get_settings

settings = get_settings()
print(settings.SUPABASE_URL)
=============================================================================
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import List

from dotenv import load_dotenv

# Load .env from the backend/ directory (parent of core/), works from any cwd
_BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=_BACKEND_DIR / ".env", override=False)


class Settings:
    """
    Centralised application settings loaded from environment variables.

    Attributes:
        APP_TITLE (str): Human-readable API title shown in the OpenAPI docs.
        APP_VERSION (str): Semver string for the current release.
        DEBUG (bool): Enable debug/reload mode when running locally.
        SUPABASE_URL (str): Supabase project URL.
        SUPABASE_KEY (str): Supabase anon or service-role key.
        FRONTEND_URL (str): Deployed frontend origin added to CORS allow-list.
        CORS_ORIGINS (List[str]): Full list of allowed CORS origins.
    """

    # ------------------------------------------------------------------
    # API metadata
    # ------------------------------------------------------------------
    APP_TITLE: str = "Investment Analytics API"
    APP_VERSION: str = "0.2.0"
    APP_DESCRIPTION: str = (
        "Backend API for the Educational Investment Platform. "
        "Provides historical prices, sync, and forecasting endpoints."
    )
    DEBUG: bool = os.environ.get("DEBUG", "false").lower() == "true"

    # ------------------------------------------------------------------
    # Supabase
    # ------------------------------------------------------------------
    SUPABASE_URL: str = os.environ.get("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.environ.get("SUPABASE_KEY", "")

    # ------------------------------------------------------------------
    # CORS
    # ------------------------------------------------------------------
    _DEFAULT_ORIGINS: List[str] = [
        "http://localhost:8501",    # Streamlit dev
        "http://localhost:5173",    # Vite / React dev
        "http://127.0.0.1:8501",
        "https://capstone-project-unfc-ashen.vercel.app",
        "https://capstone-project-unfc.vercel.app",
    ]

    @property
    def CORS_ORIGINS(self) -> List[str]:
        """Return the allowed CORS origins, injecting FRONTEND_URL if set."""
        origins = list(self._DEFAULT_ORIGINS)
        frontend_url = os.environ.get("FRONTEND_URL")
        if frontend_url:
            origins.append(frontend_url)
        return origins


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return a cached singleton Settings instance.

    The result is cached so the env file is read only once per process.

    Returns:
        Settings: Application settings instance.
    """
    return Settings()
