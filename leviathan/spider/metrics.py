"""
Prometheus metrics for Spider Node.

Minimal implementation without external dependencies.
Exposes metrics in Prometheus text format.
"""
from typing import Dict
import time


class Counter:
    """Simple counter metric."""
    
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.value = 0
    
    def inc(self, amount: int = 1):
        """Increment counter."""
        self.value += amount
    
    def render(self) -> str:
        """Render in Prometheus text format."""
        lines = [
            f"# HELP {self.name} {self.description}",
            f"# TYPE {self.name} counter",
            f"{self.name} {self.value}"
        ]
        return "\n".join(lines)


class Gauge:
    """Simple gauge metric."""
    
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.value = 0
    
    def set(self, value: float):
        """Set gauge value."""
        self.value = value
    
    def render(self) -> str:
        """Render in Prometheus text format."""
        lines = [
            f"# HELP {self.name} {self.description}",
            f"# TYPE {self.name} gauge",
            f"{self.name} {self.value}"
        ]
        return "\n".join(lines)


class MetricsRegistry:
    """Registry for Prometheus metrics."""
    
    def __init__(self):
        self.metrics: Dict[str, any] = {}
    
    def register_counter(self, name: str, description: str) -> Counter:
        """Register a counter metric."""
        counter = Counter(name, description)
        self.metrics[name] = counter
        return counter
    
    def register_gauge(self, name: str, description: str) -> Gauge:
        """Register a gauge metric."""
        gauge = Gauge(name, description)
        self.metrics[name] = gauge
        return gauge
    
    def render(self) -> str:
        """Render all metrics in Prometheus text format."""
        output = []
        for metric in self.metrics.values():
            output.append(metric.render())
        return "\n\n".join(output) + "\n"


# Global registry
registry = MetricsRegistry()

# Spider Node metrics
events_received_total = registry.register_counter(
    "leviathan_events_received_total",
    "Total number of events received by Spider Node"
)

spider_up = registry.register_gauge(
    "leviathan_spider_up",
    "Spider Node is up and running"
)

# Set spider_up to 1 on module load
spider_up.set(1)
