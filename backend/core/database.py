"""
=============================================================================
DATABASE CONNECTION - Supabase Client Factory
=============================================================================

WARNING: ISOLATION BOUNDARY
---------------------------
This module provides the Supabase client connection.
All database access should go through this module.

Phase 3/4 developers:
- You should NOT need to import this directly
- Use the API endpoints to read cached data
- If you need raw DB access, consult the data team first
=============================================================================
"""

import os
from pathlib import Path
from supabase import create_client, Client
from typing import Optional
from dotenv import load_dotenv

# Load .env from the backend/ directory (parent of core/)
_BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=_BACKEND_DIR / ".env", override=False)

# Supabase connection settings from environment
SUPABASE_URL: Optional[str] = os.environ.get("SUPABASE_URL")
SUPABASE_KEY: Optional[str] = os.environ.get("SUPABASE_KEY")


def get_supabase_client() -> Client:
    """
    Initializes and returns the Supabase client.
    
    This is a factory function that creates a new client connection.
    The client is reusable for multiple queries.
    
    Environment Variables Required:
        SUPABASE_URL: Your Supabase project URL
        SUPABASE_KEY: Your Supabase anon/service key
        
    Returns:
        Supabase Client instance
        
    Raises:
        Warning if credentials are not set (will fail on first query)
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("⚠️  Warning: SUPABASE_URL or SUPABASE_KEY not set in environment.")
        print("   Make sure you have a .env file with the correct values.")
        print("   Run 'npx supabase start' to get local credentials.")
        
    return create_client(SUPABASE_URL, SUPABASE_KEY)
