"""Health endpoints expose shared configuration and audit state."""

from fastapi import APIRouter

from ..config import APPLICATION_NAME, FEATURE_FLAGS
from ..events import EVENT_LOG

router = APIRouter()


@router.get("/health")
def health_route() -> dict:
    return {"ok": True, "name": APPLICATION_NAME, "features": FEATURE_FLAGS}


@router.get("/events")
def events_route() -> dict:
    return {"events": len(EVENT_LOG)}
