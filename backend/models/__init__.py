"""
Shared Pydantic models for API and orchestration boundaries.

- AnalysisResult: full response from analyze_conflict (DAG/CEO output)
"""

from .analysis import AnalysisResult

__all__ = ["AnalysisResult"]
