"""
Spider Node event forwarder.

Forwards event bundles to Spider Node for observability.
Best-effort, non-blocking, never fails control plane operations.
"""
import os
import logging
from typing import Dict, Any, Optional
import httpx


logger = logging.getLogger(__name__)


class SpiderForwarder:
    """Forwards events to Spider Node with best-effort delivery."""
    
    def __init__(self):
        self.enabled = os.getenv("LEVIATHAN_SPIDER_ENABLED", "false").lower() == "true"
        self.spider_url = os.getenv("LEVIATHAN_SPIDER_URL", "")
        self.timeout = 1.0  # 1 second timeout
        
        if self.enabled and not self.spider_url:
            logger.warning("LEVIATHAN_SPIDER_ENABLED=true but LEVIATHAN_SPIDER_URL not set. Disabling Spider forwarding.")
            self.enabled = False
        
        if self.enabled:
            logger.info(f"Spider forwarding enabled: {self.spider_url}")
    
    async def forward_event_bundle(self, bundle: Dict[str, Any]) -> None:
        """
        Forward event bundle to Spider Node.
        
        Best-effort delivery:
        - Short timeout (1s)
        - All exceptions caught and logged
        - Never raises exceptions
        - Returns immediately if disabled
        """
        if not self.enabled:
            return
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.spider_url}/v1/events/ingest",
                    json=bundle
                )
                
                if response.status_code == 200:
                    logger.debug(f"Forwarded event bundle to Spider: {bundle.get('bundle_id')}")
                else:
                    logger.warning(f"Spider returned {response.status_code} for bundle {bundle.get('bundle_id')}")
        
        except httpx.TimeoutException:
            logger.warning(f"Spider forwarding timeout for bundle {bundle.get('bundle_id')}")
        
        except httpx.ConnectError:
            logger.warning(f"Spider unreachable for bundle {bundle.get('bundle_id')}")
        
        except Exception as e:
            logger.warning(f"Spider forwarding error for bundle {bundle.get('bundle_id')}: {e}")


# Global forwarder instance
forwarder = SpiderForwarder()
