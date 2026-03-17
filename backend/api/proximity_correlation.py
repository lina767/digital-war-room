"""
Re-export proximity correlation for API routes (avoids circular import with agents).
Implementation lives in services.proximity_correlation.
"""

from services.proximity_correlation import run_correlation_for_events  # noqa: F401
