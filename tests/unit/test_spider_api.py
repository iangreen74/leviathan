"""
Unit tests for Spider Node API.

Tests health and metrics endpoints.
"""
import pytest
from fastapi.testclient import TestClient

from leviathan.spider.api import app
from leviathan.spider import metrics


class TestSpiderAPI:
    """Test Spider Node API endpoints."""
    
    def setup_method(self):
        """Setup test client."""
        self.client = TestClient(app)
    
    def test_health_endpoint_returns_200(self):
        """Health endpoint should return 200 OK."""
        response = self.client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "spider-node"
        assert "version" in data
    
    def test_metrics_endpoint_returns_200(self):
        """Metrics endpoint should return 200 OK."""
        response = self.client.get("/metrics")
        
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/plain; charset=utf-8"
    
    def test_metrics_includes_known_metric_names(self):
        """Metrics endpoint should include known metric names."""
        response = self.client.get("/metrics")
        
        assert response.status_code == 200
        content = response.text
        
        # Check for expected metric names
        assert "leviathan_events_received_total" in content
        assert "leviathan_spider_up" in content
    
    def test_metrics_prometheus_format(self):
        """Metrics should be in Prometheus text format."""
        response = self.client.get("/metrics")
        
        assert response.status_code == 200
        content = response.text
        
        # Check for Prometheus format markers
        assert "# HELP" in content
        assert "# TYPE" in content
        
        # Check for counter type
        assert "# TYPE leviathan_events_received_total counter" in content
        
        # Check for gauge type
        assert "# TYPE leviathan_spider_up gauge" in content
    
    def test_spider_up_gauge_is_one(self):
        """Spider up gauge should be set to 1."""
        response = self.client.get("/metrics")
        
        assert response.status_code == 200
        content = response.text
        
        # Spider should report as up
        assert "leviathan_spider_up 1" in content


class TestSpiderMetrics:
    """Test Spider Node metrics."""
    
    def test_counter_increments(self):
        """Counter should increment correctly."""
        counter = metrics.Counter("test_counter", "Test counter")
        
        assert counter.value == 0
        
        counter.inc()
        assert counter.value == 1
        
        counter.inc(5)
        assert counter.value == 6
    
    def test_gauge_sets_value(self):
        """Gauge should set value correctly."""
        gauge = metrics.Gauge("test_gauge", "Test gauge")
        
        assert gauge.value == 0
        
        gauge.set(42)
        assert gauge.value == 42
        
        gauge.set(100.5)
        assert gauge.value == 100.5
    
    def test_counter_render_prometheus_format(self):
        """Counter should render in Prometheus format."""
        counter = metrics.Counter("test_counter", "Test description")
        counter.inc(10)
        
        output = counter.render()
        
        assert "# HELP test_counter Test description" in output
        assert "# TYPE test_counter counter" in output
        assert "test_counter 10" in output
    
    def test_gauge_render_prometheus_format(self):
        """Gauge should render in Prometheus format."""
        gauge = metrics.Gauge("test_gauge", "Test description")
        gauge.set(42)
        
        output = gauge.render()
        
        assert "# HELP test_gauge Test description" in output
        assert "# TYPE test_gauge gauge" in output
        assert "test_gauge 42" in output
    
    def test_registry_renders_all_metrics(self):
        """Registry should render all registered metrics."""
        registry = metrics.MetricsRegistry()
        
        counter = registry.register_counter("test_counter", "Counter desc")
        gauge = registry.register_gauge("test_gauge", "Gauge desc")
        
        counter.inc(5)
        gauge.set(100)
        
        output = registry.render()
        
        assert "test_counter 5" in output
        assert "test_gauge 100" in output
