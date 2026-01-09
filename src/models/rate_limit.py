"""
Rate Limiting model for per-user request tracking.

Implements sliding window rate limiting to enforce
30 requests per minute per user (configurable).
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Tuple
from collections import deque


@dataclass
class RateLimitTracker:
    """
    Tracks per-user request counts for rate limiting.
    
    Uses a sliding window algorithm to track requests within
    the time window, automatically pruning old timestamps.
    
    Attributes:
        user_id: LINE user ID being tracked
        window_seconds: Time window for rate limiting (default: 60s)
        max_requests: Maximum requests allowed per window (default: 30)
        request_timestamps: Deque of request timestamps within window
    """
    
    user_id: str
    window_seconds: int = 60
    max_requests: int = 30
    request_timestamps: deque = field(default_factory=deque)
    
    def _prune_old_timestamps(self) -> None:
        """Remove timestamps older than the sliding window."""
        now = datetime.utcnow()
        cutoff = now.timestamp() - self.window_seconds
        
        # Remove old timestamps from the left (oldest first)
        while self.request_timestamps and self.request_timestamps[0] < cutoff:
            self.request_timestamps.popleft()
    
    def is_allowed(self) -> Tuple[bool, int]:
        """
        Check if a new request is allowed under rate limit.
        
        Returns:
            Tuple of (allowed: bool, seconds_until_reset: int)
            - allowed: True if request is allowed
            - seconds_until_reset: Seconds until oldest request expires (0 if allowed)
        """
        self._prune_old_timestamps()
        
        if len(self.request_timestamps) < self.max_requests:
            return (True, 0)
        
        # Calculate time until oldest request expires
        now = datetime.utcnow().timestamp()
        oldest = self.request_timestamps[0]
        seconds_until_reset = int(self.window_seconds - (now - oldest)) + 1
        
        return (False, max(0, seconds_until_reset))
    
    def record_request(self) -> None:
        """Record a new request timestamp."""
        self._prune_old_timestamps()
        self.request_timestamps.append(datetime.utcnow().timestamp())
    
    def reset(self) -> None:
        """Clear all timestamps (for testing or admin override)."""
        self.request_timestamps.clear()
    
    @property
    def current_count(self) -> int:
        """Get current request count within window."""
        self._prune_old_timestamps()
        return len(self.request_timestamps)
    
    @property
    def remaining(self) -> int:
        """Get remaining requests allowed in current window."""
        return max(0, self.max_requests - self.current_count)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for logging/debugging."""
        self._prune_old_timestamps()
        return {
            "user_id": f"{self.user_id[:4]}...{self.user_id[-4:]}" if self.user_id else None,
            "current_count": self.current_count,
            "max_requests": self.max_requests,
            "remaining": self.remaining,
            "window_seconds": self.window_seconds,
        }
