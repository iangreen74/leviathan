"""
Spider Node API.

FastAPI service providing health and metrics endpoints.
"""
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

from leviathan.spider import metrics


app = FastAPI(
    title="Leviathan Spider Node",
    description="Observability and telemetry service",
    version="1.0.0"
)


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
