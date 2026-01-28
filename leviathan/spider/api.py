"""
Spider Node API.

FastAPI service providing health and metrics endpoints.
"""
from typing import Dict, Any, List
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from leviathan.spider import metrics


app = FastAPI(
    title="Leviathan Spider Node",
    description="Observability and telemetry service",
    version="1.0.0"
)


class EventIngestRequest(BaseModel):
    """Event bundle from control plane."""
    target: str
    bundle_id: str
    events: List[Dict[str, Any]]
    artifacts: List[Dict[str, Any]] = []


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "spider-node",
        "version": "1.0.0"
    }


@app.get("/metrics", response_class=PlainTextResponse)
async def get_metrics():
    """Prometheus metrics endpoint."""
    return metrics.registry.render()


@app.post("/v1/events/ingest")
async def ingest_events(request: EventIngestRequest):
    """
    Receive event bundle from control plane.
    
    Increments metrics for observability.
    Always returns 200 OK for valid JSON.
    """
    # Increment total events counter
    metrics.events_received_total.inc(len(request.events))
    
    # Update last event timestamp
    import time
    metrics.spider_last_event_ts.set(time.time())
    
    # Increment per-event-type counters
    for event in request.events:
        event_type = event.get("event_type", "unknown")
        metrics.increment_event_type(event_type)
    
    return {"status": "ok", "received": len(request.events)}
