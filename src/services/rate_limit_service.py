"""
Rate limiting service for per-user request throttling.

Manages RateLimitTracker instances for all users and provides
rate limit checking with automatic cleanup of inactive trackers.
"""

from typing import Dict, Tuple, Optional
from datetime import datetime
import asyncio

from src.models.rate_limit import RateLimitTracker
from src.config import get_settings
from src.utils.logger import get_logger

logger = get_logger("services.rate_limit")


class RateLimitService:
    """
    Service for managing per-user rate limiting.
    
    Maintains a dictionary of RateLimitTracker instances keyed by user_id.
    Automatically cleans up trackers for inactive users to prevent memory leaks.
    
    Attributes:
        trackers: Dictionary mapping user_id to RateLimitTracker
        max_requests: Maximum requests per window (from config)
        window_seconds: Rate limit window in seconds (from config)
        cleanup_interval: Seconds between cleanup runs
    """
    
    def __init__(
        self,
        max_requests: Optional[int] = None,
        window_seconds: Optional[int] = None,
        cleanup_interval: int = 300,  # 5 minutes
    ):
        """
        Initialize rate limit service.
        
        Args:
            max_requests: Override config max_requests
            window_seconds: Override config window_seconds
            cleanup_interval: Seconds between inactive tracker cleanup
        """
        settings = get_settings()
        self.max_requests = max_requests or settings.rate_limit_max_requests
        self.window_seconds = window_seconds or settings.rate_limit_window_seconds
        self.cleanup_interval = cleanup_interval
        
        self.trackers: Dict[str, RateLimitTracker] = {}
        self._last_cleanup = datetime.utcnow()
        self._lock = asyncio.Lock()
        
        logger.info(
            f"RateLimitService initialized: {self.max_requests} req/{self.window_seconds}s"
        )
    
    def _get_or_create_tracker(self, user_id: str) -> RateLimitTracker:
        """Get existing tracker or create new one for user."""
        if user_id not in self.trackers:
            self.trackers[user_id] = RateLimitTracker(
                user_id=user_id,
                window_seconds=self.window_seconds,
                max_requests=self.max_requests,
            )
        return self.trackers[user_id]
    
    async def is_allowed(self, user_id: str) -> Tuple[bool, int, int]:
        """
        Check if request is allowed for user.
        
        Args:
            user_id: LINE user ID
            
        Returns:
            Tuple of (allowed, seconds_until_reset, remaining_requests)
        """
        async with self._lock:
            tracker = self._get_or_create_tracker(user_id)
            allowed, seconds_until_reset = tracker.is_allowed()
            remaining = tracker.remaining
            
            if not allowed:
                logger.warning(
                    f"Rate limit exceeded for user",
                    extra={
                        "user_id": user_id,
                        "remaining": remaining,
                        "reset_in": seconds_until_reset,
                    }
                )
            
            return (allowed, seconds_until_reset, remaining)
    
    async def record_request(self, user_id: str) -> int:
        """
        Record a request for rate limiting.
        
        Args:
            user_id: LINE user ID
            
        Returns:
            Remaining requests in current window
        """
        async with self._lock:
            tracker = self._get_or_create_tracker(user_id)
            tracker.record_request()
            
            # Trigger cleanup periodically
            await self._maybe_cleanup()
            
            return tracker.remaining
    
    async def check_and_record(self, user_id: str) -> Tuple[bool, int, int]:
        """
        Check rate limit and record request if allowed.
        
        Convenience method combining is_allowed and record_request.
        
        Args:
            user_id: LINE user ID
            
        Returns:
            Tuple of (allowed, seconds_until_reset, remaining_requests)
        """
        async with self._lock:
            tracker = self._get_or_create_tracker(user_id)
            allowed, seconds_until_reset = tracker.is_allowed()
            
            if allowed:
                tracker.record_request()
            
            remaining = tracker.remaining
            
            if not allowed:
                logger.warning(
                    f"Rate limit check failed",
                    extra={
                        "user_id": user_id,
                        "reset_in": seconds_until_reset,
                    }
                )
            
            await self._maybe_cleanup()
            return (allowed, seconds_until_reset, remaining)
    
    async def reset_user(self, user_id: str) -> None:
        """
        Reset rate limit for a specific user (admin override).
        
        Args:
            user_id: LINE user ID to reset
        """
        async with self._lock:
            if user_id in self.trackers:
                self.trackers[user_id].reset()
                logger.info(f"Rate limit reset for user")
    
    async def _maybe_cleanup(self) -> None:
        """Clean up inactive trackers if enough time has passed."""
        now = datetime.utcnow()
        elapsed = (now - self._last_cleanup).total_seconds()
        
        if elapsed < self.cleanup_interval:
            return
        
        self._last_cleanup = now
        
        # Remove trackers with zero active requests
        inactive_users = [
            user_id for user_id, tracker in self.trackers.items()
            if tracker.current_count == 0
        ]
        
        for user_id in inactive_users:
            del self.trackers[user_id]
        
        if inactive_users:
            logger.debug(
                f"Cleaned up {len(inactive_users)} inactive rate limit trackers"
            )
    
    def get_stats(self) -> dict:
        """Get service statistics for monitoring."""
        return {
            "active_trackers": len(self.trackers),
            "max_requests": self.max_requests,
            "window_seconds": self.window_seconds,
        }


# Global singleton instance
_rate_limit_service: Optional[RateLimitService] = None


def get_rate_limit_service() -> RateLimitService:
    """Get or create the global RateLimitService instance."""
    global _rate_limit_service
    if _rate_limit_service is None:
        _rate_limit_service = RateLimitService()
    return _rate_limit_service
