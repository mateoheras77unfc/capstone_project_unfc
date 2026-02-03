# Project Folder Structure

To support parallel development and modularity, the project will follow this structure. This ensures that the Data Engine (Phase 1) is decoupled from the Analytics (Phase 3 & 4) and the UI (Phase 2).

```text
capstone_project_unfc/
├── .github/                # CI/CD workflows
├── backend/                # Primary Python Logic
│   ├── app/                # Main application entry
│   ├── core/               # Shared logic (Supabase client, Config)
│   ├── data_engine/        # Phase 1: yfinance fetchers & storage logic
│   ├── analytics/          # Phase 3 & 4: Model-agnostic engines
│   │   ├── forecasting/    # Teams can drop new model files here
│   │   └── optimization/   # Multi-asset alignment & weights logic
│   ├── api/                # API routes (FastAPI) or Service layer
│   └── scripts/            # Database migration or one-off data scripts
├── frontend/               # Phase 2: React/Next.js or Streamlit UI
│   ├── components/         # Reusable UI elements (Tables, Charts)
│   ├── pages/              # Main dashboard views
│   └── services/           # Frontend API clients
├── docs/                   # Documentation (Phases, API info, etc.)
├── tests/                  # Unit tests for each module
├── .python-version         # For uv/pyenv
└── pyproject.toml          # Package management (managed by uv)
```

## Modular Philosophy
*   **Decoupled Analytics:** The `analytics/` folder contains subfolders for each feature. Each model should be a separate file or class that follows a standard interface.
*   **Persistence Layer:** All database interactions should live in `core/` or `data_engine/`, so the analytics teams don't need to write raw SQL.
*   **Separation of Concerns:** The `frontend/` should never talk to `yfinance` directly; it only consumes data from the `backend/` or `Supabase`.

## Implementation Order
1.  Initialize `pyproject.toml` with `uv`.
2.  Set up the `backend/core/` and `backend/data_engine/` folders.
3.  Establish `frontend/` basic scaffolding.
