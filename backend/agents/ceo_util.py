"""Shared helpers for CEO / DAG result coercion."""

from typing import Any, Dict


def as_dict(result: Any) -> Dict[str, Any]:
    if result is None:
        return {}
    if isinstance(result, dict):
        return result
    if hasattr(result, "model_dump"):
        return result.model_dump(mode="json")
    if hasattr(result, "data") and isinstance(result.data, dict):
        return result.data
    return {}
