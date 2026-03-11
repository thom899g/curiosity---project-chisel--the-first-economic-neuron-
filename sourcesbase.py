"""
Abstract base class for all data sources.
Ensures consistent error handling, retry logic, and metrics collection.
"""
import asyncio
import time
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from datetime import datetime

import structlog
from pydantic import ValidationError

from config import SourceConfig
from schemas import AssetSnapshot, AssetRiskClass

logger = structlog.get_logger()


class SourceException(Exception):
    """Base exception for source failures."""
    pass


class RateLimitException(SourceException):
    """Source rate limit exceeded."""
    pass


class AuthenticationException(SourceException):
    """API authentication failed."""
    pass


class BaseSource(ABC):
    """
    Abstract source with built-in retry, latency tracking, and confidence scoring.
    """
    
    def __init__(self, config: SourceConfig):
        self.config = config
        self.source_name = config.name
        self._request_count = 0
        self._error_count = 0
        self._last_request_time: Optional[datetime] = None
        
    async def fetch_snapshot(self) -> List[AssetSnapshot]:
        """
        Public method with built-in retry logic and metrics collection.
        Returns validated AssetSnapshots or empty list on failure.
        """
        start_time = time.time()
        
        for attempt in range(self.config.retry_attempts + 1):
            try:
                self._request_count += 1
                self._last_request_time = datetime.utcnow()
                
                # Rate limiting (basic)
                if attempt > 0:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.warning(
                        "retry_attempt",
                        source=self.source_name,
                        attempt=attempt,
                        wait_seconds=wait_time
                    )
                    await asyncio.sleep(wait_time)
                
                # Fetch raw data from implementation
                raw_data = await self._fetch_raw()
                
                # Validate and normalize
                snapshots = self._normalize_to_schema(raw