"""
Entry point for local development.

Run with:
    python main.py
    -- or --
    uvicorn backend.app.main:app --reload
"""

import uvicorn


def main() -> None:
    """Start the FastAPI development server with hot-reload."""
    uvicorn.run(
        "backend.app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level="info",
    )


if __name__ == "__main__":
    main()
