"""
CEO orchestrator – public façade.

Implementation is split across ``ceo_config``, ``ceo_dag``, ``ceo_synthesize``,
``ceo_prompt``, ``ceo_llm``, ``ceo_response``, ``ceo_scoring``, and ``ceo_util``.
"""

from .ceo_config import CEO_LEGACY_AGENT_WEIGHTS, CEO_WEIGHTS
from .ceo_dag import (
    _all_divisions,
    _build_full_dag,
    analyze_conflict_dag,
    analyze_conflict_dag_streaming,
)
from .ceo_prompt import build_ceo_prompt as _build_ceo_prompt
from .ceo_synthesize import _ceo_synthesize

# Backwards compatibility for tests and callers
__all__ = [
    "CEO_LEGACY_AGENT_WEIGHTS",
    "CEO_WEIGHTS",
    "_all_divisions",
    "_build_full_dag",
    "_build_ceo_prompt",
    "_ceo_synthesize",
    "analyze_conflict_dag",
    "analyze_conflict_dag_streaming",
]
