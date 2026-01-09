"""
Message Cache Service for storing recent messages to support quote/reply feature.

LINE doesn't provide quoted message content in webhooks, so we cache
recent messages to retrieve them when users reply to messages.
"""

from collections import OrderedDict
import time
from typing import Optional, Dict, Any

# Message cache: {message_id: {"text": str, "type": str, "timestamp": float}}
_message_cache: OrderedDict = OrderedDict()
_MAX_CACHE_SIZE = 100  # Keep last 100 messages
_CACHE_TTL_SECONDS = 3600  # 1 hour


def cache_message(message_id: str, message_type: str, text: Optional[str] = None) -> None:
    """
    Cache a message for later retrieval in quote feature.

    Args:
        message_id: LINE message ID
        message_type: Message type (text, image, etc.)
        text: Message text content (only for text messages)
    """
    _message_cache[message_id] = {
        "type": message_type,
        "text": text,
        "timestamp": time.time(),
    }

    # Cleanup old entries if cache is too large
    if len(_message_cache) > _MAX_CACHE_SIZE:
        _message_cache.popitem(last=False)  # Remove oldest

    # Remove expired entries
    current_time = time.time()
    expired_keys = [
        k for k, v in _message_cache.items()
        if current_time - v["timestamp"] > _CACHE_TTL_SECONDS
    ]
    for k in expired_keys:
        _message_cache.pop(k, None)


def get_cached_message(message_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a cached message.

    Args:
        message_id: LINE message ID

    Returns:
        Dict with keys: type, text, timestamp or None if not found
    """
    return _message_cache.get(message_id)


def get_cache_stats() -> Dict[str, Any]:
    """
    Get cache statistics.

    Returns:
        Dict with cache size and other stats
    """
    return {
        "size": len(_message_cache),
        "max_size": _MAX_CACHE_SIZE,
        "ttl_seconds": _CACHE_TTL_SECONDS,
    }


def clear_cache() -> None:
    """Clear all cached messages."""
    _message_cache.clear()
