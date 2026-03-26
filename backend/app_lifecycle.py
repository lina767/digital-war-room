import asyncio
import logging
import time

from agents.pattern_anomalies import attach_pattern_flags
from agents.supervisor import analyze_conflict
from api.routes import push_agent_status, push_escalation_timeline, push_run_history
from services.analysis_side_effects import persist_analysis_side_effects
from services.request_context import RequestContext, reset_request_context, set_request_context
from services.tenant_constants import get_default_tenant_id


def create_periodic_analysis_task(
    app,
    *,
    conflict: str,
    interval_sec: int,
    timeout_sec: int,
    logger: logging.Logger,
) -> asyncio.Task:
    async def run_periodic_analysis():
        loop = asyncio.get_running_loop()
        await asyncio.sleep(5)
        consecutive_failures = 0
        while True:
            try:
                try:
                    from services.haiku_service import reset_run_counters, log_run_stats

                    reset_run_counters()
                except Exception:
                    pass
                try:
                    from services.hf_service import warmup

                    await warmup()
                except Exception:
                    pass

                def _run_auto():
                    tid = get_default_tenant_id()
                    ctx = RequestContext(tenant_id=tid, user_id=None, role="viewer", auth_method="default")
                    tok = set_request_context(ctx)
                    try:
                        return analyze_conflict(conflict)
                    finally:
                        reset_request_context(tok)

                _ntid = get_default_tenant_id()
                run_key = f"{_ntid}\n{conflict}"
                if run_key in app.state.analysis_inflight:
                    logger.info("Periodic analysis skipped for %s: run already in progress.", conflict)
                    await asyncio.sleep(min(60, interval_sec))
                    continue
                app.state.analysis_inflight[run_key] = time.time()
                try:
                    result = await asyncio.wait_for(loop.run_in_executor(None, _run_auto), timeout=float(timeout_sec))
                finally:
                    app.state.analysis_inflight.pop(run_key, None)

                at_ts = time.time()
                attach_pattern_flags(app.state.state_service, conflict, result, tenant_id=_ntid)
                app.state.state_service.set_cache(conflict, result, at_ts, tenant_id=_ntid)
                app.state.state_service.pop_last_error(conflict, tenant_id=_ntid)
                push_escalation_timeline(app.state, conflict, at_ts, result, tenant_id=_ntid)
                push_agent_status(app.state, result, tenant_id=_ntid)
                push_run_history(app.state, conflict, at_ts, result, tenant_id=_ntid)
                await app.state.ws_manager.broadcast({**result, "status": "ok", "conflict": conflict})
                try:
                    await persist_analysis_side_effects(conflict, result)
                except Exception:
                    pass

                try:
                    from services.haiku_service import log_run_stats

                    log_run_stats()
                except Exception:
                    pass

                logger.info("Analysis for %s done.", conflict)
                consecutive_failures = 0
                await asyncio.sleep(interval_sec)
            except asyncio.TimeoutError:
                consecutive_failures += 1
                retry_delay = min(60 * (2 ** (consecutive_failures - 1)), interval_sec)
                logger.warning(
                    "Periodic analysis timed out after %ss (attempt %d). Retrying in %ds.",
                    timeout_sec,
                    consecutive_failures,
                    retry_delay,
                )
                await asyncio.sleep(retry_delay)
            except Exception as e:
                consecutive_failures += 1
                retry_delay = min(60 * (2 ** (consecutive_failures - 1)), interval_sec)
                logger.warning("Analysis failed (attempt %d): %s. Retrying in %ds.", consecutive_failures, e, retry_delay)
                await asyncio.sleep(retry_delay)

    return asyncio.create_task(run_periodic_analysis())
