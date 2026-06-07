"""
Tarzan background worker.

Runs scheduled sync jobs for Jira and GitLab. On startup it loads all active
connector configs and schedules per-connector jobs at the configured interval.
Also subscribes to a Redis pub/sub channel for on-demand sync triggers.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .jira_sync import sync_jira
from .gitlab_sync import sync_gitlab
from app.config import get_settings

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.processors.JSONRenderer(),
    ]
)
log = structlog.get_logger()
settings = get_settings()

scheduler = AsyncIOScheduler()


async def run_all_syncs() -> None:
    """Run both Jira and GitLab syncs sequentially."""
    try:
        await sync_jira()
    except Exception as exc:
        log.error("jira_sync_error", error=str(exc))
    try:
        await sync_gitlab()
    except Exception as exc:
        log.error("gitlab_sync_error", error=str(exc))


async def redis_listener() -> None:
    """Listen for manual sync triggers published to tarzan:sync."""
    import redis.asyncio as aioredis

    r = aioredis.from_url(settings.REDIS_URL)
    pubsub = r.pubsub()
    await pubsub.subscribe("tarzan:sync")
    log.info("redis_listener_started")
    async for message in pubsub.listen():
        if message["type"] == "message":
            log.info("manual_sync_triggered")
            await run_all_syncs()
    await r.aclose()


async def main() -> None:
    log.info("worker_startup", env=settings.ENVIRONMENT)

    # Schedule periodic sync
    scheduler.add_job(
        run_all_syncs,
        trigger="interval",
        seconds=settings.WORKER_POLL_INTERVAL_SECONDS,
        id="full_sync",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    scheduler.start()

    # Run an immediate sync on startup
    asyncio.create_task(run_all_syncs())

    # Redis listener in background
    asyncio.create_task(redis_listener())

    # Wait forever
    stop_event = asyncio.Event()

    def _shutdown(*_) -> None:
        log.info("worker_shutdown_signal")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, _shutdown)

    await stop_event.wait()
    scheduler.shutdown(wait=False)
    log.info("worker_stopped")


if __name__ == "__main__":
    asyncio.run(main())