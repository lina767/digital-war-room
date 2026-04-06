"""Startup/shutdown background task orchestration for app lifespan."""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Any

from agents.config import GREYNOISE_API_KEY, GREYNOISE_SCHEDULER_INTERVAL_SEC
from app_lifecycle import create_periodic_analysis_task
from services.http_client import get_http_client
from settings import settings


@dataclass
class StartupTasks:
    acled_task: asyncio.Task[Any]
    analysis_task: asyncio.Task[Any]
    worker_task: asyncio.Task[Any]
    greynoise_task: asyncio.Task[Any] | None = None
    greynoise_discovery_task: asyncio.Task[Any] | None = None
    newsletter_task: asyncio.Task[Any] | None = None
    newsletter_reminder_task: asyncio.Task[Any] | None = None
    retention_task: asyncio.Task[Any] | None = None

    def as_list(self) -> list[asyncio.Task[Any]]:
        out = [self.analysis_task, self.worker_task, self.acled_task]
        if self.greynoise_task:
            out.append(self.greynoise_task)
        if self.greynoise_discovery_task:
            out.append(self.greynoise_discovery_task)
        if self.newsletter_task:
            out.append(self.newsletter_task)
        if self.newsletter_reminder_task:
            out.append(self.newsletter_reminder_task)
        if self.retention_task:
            out.append(self.retention_task)
        return out


def _create_acled_task(logger: logging.Logger) -> asyncio.Task[Any]:
    # Defer ACLED download/parse to a background task so ASGI can bind quickly for healthchecks.
    async def _acled_startup_refresh() -> None:
        try:
            from services.acled_aggregated import refresh_acled_aggregated

            await asyncio.to_thread(refresh_acled_aggregated)
            logger.info("ACLED aggregated data checked/refreshed at startup")
        except Exception as e:
            logger.warning("ACLED aggregated startup refresh failed: %s", e)

    return asyncio.create_task(_acled_startup_refresh())


def _create_greynoise_tasks(logger: logging.Logger) -> tuple[asyncio.Task[Any] | None, asyncio.Task[Any] | None]:
    if not GREYNOISE_API_KEY:
        return None, None

    async def run_greynoise_scheduler() -> None:
        from agents.greynoise_agent import run_greynoise_scheduler_cycle

        await asyncio.sleep(15)
        while True:
            try:
                await run_greynoise_scheduler_cycle()
                logger.info("GreyNoise scheduler cycle complete.")
            except Exception as e:
                logger.warning("GreyNoise scheduler error: %s", e)
            await asyncio.sleep(GREYNOISE_SCHEDULER_INTERVAL_SEC)

    async def run_greynoise_tag_discovery() -> None:
        from agents.greynoise_agent import run_tag_discovery_cycle

        await asyncio.sleep(60)
        while True:
            try:
                await run_tag_discovery_cycle()
            except Exception as e:
                logger.warning("GreyNoise tag discovery error: %s", e)
            await asyncio.sleep(86400)  # once daily

    return asyncio.create_task(run_greynoise_scheduler()), asyncio.create_task(run_greynoise_tag_discovery())


def _create_retention_task(logger: logging.Logger) -> asyncio.Task[Any] | None:
    if not settings.retention_enabled:
        return None

    async def _retention_loop() -> None:
        from services.retention_worker import run_retention_once

        await asyncio.sleep(30)
        while True:
            try:
                result = await run_retention_once()
                logger.info("Retention job completed: %s", result)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("Retention job error: %s", e)
            await asyncio.sleep(settings.retention_interval_sec)

    return asyncio.create_task(_retention_loop())


def _seconds_until_next_newsletter_send(logger: logging.Logger) -> float:
    """
    Next run: default 10:00 in Europe/Berlin (CET/CEST). Override via
    NEWSLETTER_SEND_TIMEZONE, NEWSLETTER_SEND_HOUR, NEWSLETTER_SEND_MINUTE.
    Legacy: if NEWSLETTER_SEND_UTC_HOUR is set, use that UTC hour instead.
    """
    if "NEWSLETTER_SEND_UTC_HOUR" in os.environ:
        try:
            send_hour = int(os.getenv("NEWSLETTER_SEND_UTC_HOUR", "6"), 10)
        except ValueError:
            send_hour = 6
        send_hour = max(0, min(23, send_hour))
        now = datetime.now(timezone.utc)
        next_run = now.replace(hour=send_hour, minute=0, second=0, microsecond=0)
        if next_run <= now:
            next_run = next_run + timedelta(days=1)
        return max(60.0, (next_run - now).total_seconds())

    tz_name = settings.newsletter_send_timezone
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        logger.warning("Invalid NEWSLETTER_SEND_TIMEZONE=%r; using Europe/Berlin", tz_name)
        tz = ZoneInfo("Europe/Berlin")
    hour = settings.newsletter_send_hour
    minute = settings.newsletter_send_minute
    now = datetime.now(tz)
    next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if next_run <= now:
        next_run = next_run + timedelta(days=1)
    return max(60.0, (next_run - now).total_seconds())


def _create_newsletter_tasks(app: Any, logger: logging.Logger) -> tuple[asyncio.Task[Any] | None, asyncio.Task[Any] | None]:
    newsletter_task: asyncio.Task[Any] | None = None
    newsletter_reminder_task: asyncio.Task[Any] | None = None
    if not (os.getenv("RESEND_API_KEY") or "").strip() or not (os.getenv("NEWSLETTER_FROM") or "").strip():
        return newsletter_task, newsletter_reminder_task

    try:
        from services.newsletter_sender import log_newsletter_deliverability_hints

        log_newsletter_deliverability_hints()
    except Exception:
        pass

    if settings.newsletter_in_process_scheduler:
        first_delay = _seconds_until_next_newsletter_send(logger)
        if "NEWSLETTER_SEND_UTC_HOUR" in os.environ:
            logger.info(
                "Newsletter in-process scheduler: NEWSLETTER_SEND_UTC_HOUR=%s (UTC); first run in %.0f s",
                os.getenv("NEWSLETTER_SEND_UTC_HOUR"),
                first_delay,
            )
        else:
            logger.info(
                "Newsletter in-process scheduler: daily send at %02d:%02d %s; first run in %.0f s",
                settings.newsletter_send_hour,
                settings.newsletter_send_minute,
                settings.newsletter_send_timezone,
                first_delay,
            )

        async def _newsletter_loop() -> None:
            from api.routes_newsletter import run_daily_newsletter_job

            while True:
                delay = _seconds_until_next_newsletter_send(logger)
                await asyncio.sleep(delay)
                try:
                    conflicts, sent, skipped_dup = await run_daily_newsletter_job(app.state)
                    if skipped_dup:
                        logger.info("Newsletter daily job: skipped (already completed today)")
                    elif conflicts or sent:
                        logger.info("Newsletter daily job: conflicts=%s sent=%d", conflicts, sent)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.warning("Newsletter daily job error: %s", e)

        newsletter_task = asyncio.create_task(_newsletter_loop())
    else:
        logger.info(
            "Newsletter in-process scheduler disabled (NEWSLETTER_IN_PROCESS_SCHEDULER=false); "
            "use cron for POST /api/newsletter/send-daily"
        )

    async def _newsletter_reminder_loop() -> None:
        from services.newsletter_sender import send_confirmation_email
        from services.newsletter_store import list_pending_reminder_candidates, mark_confirmation_reminder_sent

        await asyncio.sleep(60)
        while True:
            try:
                candidates = list_pending_reminder_candidates(
                    min_age_hours=settings.newsletter_reminder_hours,
                    limit=settings.newsletter_reminder_batch_size,
                )
                reminded = 0
                for row in candidates:
                    sent = await send_confirmation_email(
                        row["email"],
                        row["conflict"],
                        row["confirm_token"],
                        reminder=True,
                    )
                    if sent and mark_confirmation_reminder_sent(row["email"], row["confirm_token"], tenant_id=row.get("tenant_id")):
                        reminded += 1
                if candidates:
                    logger.info(
                        "Newsletter reminder sweep: candidates=%d reminded=%d (age>= %dh)",
                        len(candidates),
                        reminded,
                        settings.newsletter_reminder_hours,
                    )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("Newsletter reminder loop error: %s", e)
            await asyncio.sleep(settings.newsletter_reminder_check_interval_sec)

    newsletter_reminder_task = asyncio.create_task(_newsletter_reminder_loop())
    return newsletter_task, newsletter_reminder_task


def start_startup_tasks(app: Any, logger: logging.Logger) -> StartupTasks:
    acled_task = _create_acled_task(logger)
    analysis_task = create_periodic_analysis_task(
        app,
        conflict=settings.auto_analyze_conflict,
        interval_sec=settings.auto_analyze_interval_sec,
        timeout_sec=settings.auto_analyze_timeout_sec,
        logger=logger,
    )
    worker_task = asyncio.create_task(app.state.job_queue.worker())
    greynoise_task, greynoise_discovery_task = _create_greynoise_tasks(logger)
    retention_task = _create_retention_task(logger)
    newsletter_task, newsletter_reminder_task = _create_newsletter_tasks(app, logger)
    # Ensure shared HTTP client is created early (so DNS pools etc. warm up).
    get_http_client()
    return StartupTasks(
        acled_task=acled_task,
        analysis_task=analysis_task,
        worker_task=worker_task,
        greynoise_task=greynoise_task,
        greynoise_discovery_task=greynoise_discovery_task,
        newsletter_task=newsletter_task,
        newsletter_reminder_task=newsletter_reminder_task,
        retention_task=retention_task,
    )


async def stop_startup_tasks(tasks: StartupTasks) -> None:
    for task in tasks.as_list():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
