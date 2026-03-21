"""
FastAPI dependencies for application state.

Use these with Depends() instead of getattr(request.app.state, ...) in route handlers.
Attributes are set in main.lifespan.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from services.job_queue import JobQueue
from services.state_service import StateService


def get_state_service(request: Request) -> StateService:
    return request.app.state.state_service


def get_job_queue(request: Request) -> JobQueue:
    return request.app.state.job_queue


def get_ws_manager(request: Request):
    """WebSocket broadcast manager (ConnectionManager defined in main)."""
    return request.app.state.ws_manager


StateServiceDep = Annotated[StateService, Depends(get_state_service)]
JobQueueDep = Annotated[JobQueue, Depends(get_job_queue)]
WsManagerDep = Annotated[object, Depends(get_ws_manager)]
