# Spider Node v1

**Last Updated:** 2026-01-28  
**Status:** Canonical

---

## What is Spider Node?

Spider Node is a standalone observability and telemetry service for Leviathan. It exposes health and metrics endpoints for monitoring system operation.

**Current State (v1):**
- ✅ Standalone FastAPI service
- ✅ Health check endpoint
- ✅ Prometheus metrics endpoint
- ⚠️ No control plane integration (future)

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Kubernetes Cluster                    │
│                                                          │
│  ┌────────────────┐         ┌──────────────────┐       │
│  │  Spider Node   │         │  Control Plane   │       │
│  │  (Deployment)  │         │  (Deployment)    │       │
│  │  Port 8001     │         │  Port 8000       │       │
│  │                │         │                  │       │
│  │  /health       │         │  (no integration │       │
│  │  /metrics      │         │   in v1)         │       │
│  └────────────────┘         └──────────────────┘       │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

---

## Endpoints

### GET /health

Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "service": "spider-node",
  "version": "1.0.0"
}
```

### GET /metrics

Prometheus metrics endpoint in text format.

**Metrics Exposed:**
- `leviathan_spider_up` (gauge) - Spider Node is running (value: 1)
- `leviathan_events_received_total` (counter) - Total events received (v1: always 0)

**Response:**
```
# HELP leviathan_spider_up Spider Node is up and running
# TYPE leviathan_spider_up gauge
leviathan_spider_up 1

# HELP leviathan_events_received_total Total number of events received by Spider Node
# TYPE leviathan_events_received_total counter
leviathan_events_received_total 0
```

---

## Deployment

### Local Development

```bash
# Run Spider Node locally
python3 -m leviathan.spider

# Access endpoints
curl http://localhost:8001/health
curl http://localhost:8001/metrics
```

### Kubernetes (kind)

```bash
# Deploy Spider Node
kubectl apply -f ops/k8s/spider/deployment.yaml
kubectl apply -f ops/k8s/spider/service.yaml

# Wait for ready
kubectl -n leviathan wait --for=condition=ready pod -l app=leviathan-spider --timeout=60s

# Check status
kubectl -n leviathan get pods -l app=leviathan-spider

# View logs
kubectl -n leviathan logs -l app=leviathan-spider --tail=50

# Port-forward to access locally
kubectl -n leviathan port-forward svc/leviathan-spider 8001:8001

# Test endpoints
curl http://localhost:8001/health
curl http://localhost:8001/metrics
```

---

## Configuration

**Kubernetes Deployment:**
- **Namespace:** `leviathan`
- **Image:** `leviathan-worker:local` (reuses worker image)
- **Port:** 8001
- **Replicas:** 1
- **Resources:**
  - Requests: 128Mi memory, 100m CPU
  - Limits: 256Mi memory, 200m CPU

**Probes:**
- **Liveness:** `GET /health` every 30s (initial delay 10s)
- **Readiness:** `GET /health` every 10s (initial delay 5s)

---

## Metrics Implementation

Spider Node implements a minimal Prometheus metrics exporter without external dependencies.

**Classes:**
- `Counter` - Monotonically increasing counter
- `Gauge` - Value that can go up or down
- `MetricsRegistry` - Registry for all metrics

**Format:** Prometheus text format (compatible with Prometheus scraping)

---

## Future Enhancements (Not in v1)

### Control Plane Integration
- Subscribe to control plane event stream
- Increment `leviathan_events_received_total` on events
- Add metrics for event types, targets, success/failure rates

### Additional Metrics
- `leviathan_attempts_total` - Total attempts by status
- `leviathan_prs_created_total` - Total PRs created
- `leviathan_tasks_selected_total` - Total tasks selected
- `leviathan_scheduler_cycles_total` - Total scheduler cycles

### Alerting
- Prometheus AlertManager integration
- Alert on consecutive failures
- Alert on circuit breaker trips

---

## Troubleshooting

### Spider Node Not Starting

```bash
# Check pod status
kubectl -n leviathan describe pod -l app=leviathan-spider

# View logs
kubectl -n leviathan logs -l app=leviathan-spider --tail=100
```

**Common issues:**
- Image not loaded into kind: `kind load docker-image leviathan-worker:local --name leviathan`
- Port conflict: Check if port 8001 is already in use
- Resource limits: Check if cluster has available resources

### Metrics Not Updating

In v1, metrics are static (no control plane integration). `leviathan_events_received_total` will always be 0.

Future versions will integrate with control plane to update metrics dynamically.

---

## Testing

```bash
# Run Spider Node tests
python3 -m pytest tests/unit/test_spider_api.py -v

# Run all tests
python3 -m pytest tests/unit -q
```

---

## References

- **Module:** `leviathan/spider/`
- **API:** `leviathan/spider/api.py`
- **Metrics:** `leviathan/spider/metrics.py`
- **Manifests:** `ops/k8s/spider/`
- **Tests:** `tests/unit/test_spider_api.py`
