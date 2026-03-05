import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple


JobPayload = Dict[str, Any]
JobResult = Dict[str, Any]
JobHandler = Callable[[JobPayload], Awaitable[JobResult]]


@dataclass
class Job:
    id: str
    type: str
    payload: JobPayload
    status: str = "queued"  # queued | running | done | failed
    result: Optional[JobResult] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None


class JobQueue:
    """Very lightweight in-process async job queue for long-running tasks."""

    def __init__(self) -> None:
        self._queue: "asyncio.Queue[Tuple[Job, JobHandler]]" = asyncio.Queue()
        self._jobs: Dict[str, Job] = {}
        self._lock = asyncio.Lock()

    async def enqueue(self, job_type: str, payload: JobPayload, handler: JobHandler) -> Job:
        job = Job(id=str(uuid.uuid4()), type=job_type, payload=payload)
        async with self._lock:
            self._jobs[job.id] = job
        await self._queue.put((job, handler))
        return job

    async def get_job(self, job_id: str) -> Optional[Job]:
        async with self._lock:
            return self._jobs.get(job_id)

    async def worker(self) -> None:
        """Background worker loop. Intended to be run once at startup."""
        while True:
            job, handler = await self._queue.get()
            job.started_at = time.time()
            job.status = "running"
            try:
                job.result = await handler(job.payload)
                job.status = "done"
            except Exception as e:  # pragma: no cover - defensive
                job.error = str(e)
                job.status = "failed"
            finally:
                job.finished_at = time.time()
                self._queue.task_done()

