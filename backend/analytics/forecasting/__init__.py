"""
analytics/forecasting
────────────────────
Time series forecasting models (Chronos, Prophet, etc.).

Teams can drop new model modules here; each should follow a common interface.
"""

from . import chronos2

__all__: list[str] = ["chronos2"]
