"""
Domain runner: run a set of analysts in parallel, then a manager.

Use this to structure an agent as:
  - Analysts: narrow tasks (one source or one method), return partial results.
  - Manager: takes all analyst results and produces the full domain result (score, summary, lists).

Example (conceptual):
  run_news_agent(conflict, context) ->
    run_domain_with_analysts(
      conflict=conflict,
      context=context,
      analysts=[newsapi_analyst, rss_analyst, ...],
      manager=news_manager,
      analyst_timeout_s=35,
    )
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)

# Type: (conflict, context?) -> partial result dict
AnalystFn = Callable[..., Dict[str, Any]]
# Type: (conflict, analyst_results, context?) -> full domain result dict
ManagerFn = Callable[..., Dict[str, Any]]


def _run_analyst_safe(conflict: str, context: Any, fn: AnalystFn) -> Dict[str, Any]:
    """Run analyst with optional context; fall back to fn(conflict) if analyst does not accept context."""
    if context is not None:
        try:
            return fn(conflict, context)
        except TypeError:
            pass
    return fn(conflict)


def run_domain_with_analysts(
    conflict: str,
    *,
    analysts: List[tuple[str, AnalystFn]],
    manager: ManagerFn,
    context: Any = None,
    analyst_timeout_s: float = 35.0,
    max_workers: int = 8,
) -> Dict[str, Any]:
    """
    Run all analysts in parallel, collect results, then run the manager.

    - analysts: List of (name, callable). Callable is (conflict) or (conflict, context).
    - manager: (conflict, analyst_results: Dict[str, Any], context?) -> full result.
    - Returns whatever the manager returns (must match the domain contract).
    """
    analyst_results: Dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {}
        for name, fn in analysts:
            try:
                fut = pool.submit(_run_analyst_safe, conflict, context, fn)
                futures[fut] = name
            except Exception as e:
                logger.warning("Domain runner: failed to submit analyst %s: %s", name, e)
                analyst_results[name] = {"error": str(e)}
        for fut in futures:
            name = futures[fut]
            try:
                analyst_results[name] = fut.result(timeout=analyst_timeout_s)
            except FuturesTimeoutError:
                logger.warning("Domain runner: analyst %s timed out after %ss", name, analyst_timeout_s)
                analyst_results[name] = {"error": "timeout"}
            except Exception as e:
                logger.warning("Domain runner: analyst %s failed: %s", name, e)
                analyst_results[name] = {"error": str(e)}

    try:
        if context is not None:
            try:
                return manager(conflict, analyst_results, context)
            except TypeError:
                return manager(conflict, analyst_results)
        return manager(conflict, analyst_results)
    except Exception as e:
        logger.exception("Domain runner: manager failed: %s", e)
        raise
