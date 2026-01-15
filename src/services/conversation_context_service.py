"""
Conversation Context Service for storing recent chat history.

Stores the last N messages per group/room to provide conversation context
to the LLM, helping it understand the ongoing discussion and provide
more contextually relevant responses.
"""

from collections import OrderedDict, deque
from typing import Optional, Dict, Any, List
import time

from src.utils.logger import get_logger

logger = get_logger("services.conversation_context")

# Context storage: {group_id: deque of messages}
_context_store: Dict[str, deque] = {}
_MAX_MESSAGES_PER_GROUP = 3  # Keep last 3 messages per group
_CONTEXT_TTL_SECONDS = 3600  # 1 hour


class ConversationMessage:
    """
    Represents a single message in conversation history.

    Attributes:
        user_id: LINE user ID who sent the message
        text: Message text content (or description for non-text messages)
        timestamp: When the message was sent
        message_type: Type of message (text, image, sticker, etc.)
    """

    def __init__(
        self,
        user_id: str,
        text: str,
        timestamp: float,
        message_type: str = "text"
    ):
        self.user_id = user_id
        self.text = text
        self.timestamp = timestamp
        self.message_type = message_type

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "user_id": self.user_id,
            "text": self.text,
            "timestamp": self.timestamp,
            "message_type": self.message_type,
        }

    def is_expired(self, ttl_seconds: int) -> bool:
        """Check if this message has expired."""
        return (time.time() - self.timestamp) > ttl_seconds


def add_message(
    group_id: str,
    user_id: str,
    text: str,
    message_type: str = "text"
) -> None:
    """
    Add a message to the conversation context for a group.

    Automatically maintains the maximum size (keeps only the most recent N messages)
    and removes expired messages.

    Args:
        group_id: LINE group/room ID
        user_id: LINE user ID who sent the message
        text: Message text content
        message_type: Type of message (default: "text")
    """
    # Initialize deque for this group if not exists
    if group_id not in _context_store:
        _context_store[group_id] = deque(maxlen=_MAX_MESSAGES_PER_GROUP)

    # Create message object
    message = ConversationMessage(
        user_id=user_id,
        text=text,
        timestamp=time.time(),
        message_type=message_type
    )

    # Add to deque (automatically removes oldest if at max capacity)
    _context_store[group_id].append(message)

    # Clean up expired messages from all groups
    _cleanup_expired_messages()

    # Log current context for this group
    _log_current_context(group_id)


def get_context(group_id: str, max_messages: int = 5) -> List[ConversationMessage]:
    """
    Get recent conversation history for a group.

    Args:
        group_id: LINE group/room ID
        max_messages: Maximum number of messages to return (default: 5)

    Returns:
        List of ConversationMessage objects, ordered from oldest to newest
    """
    if group_id not in _context_store:
        return []

    messages = list(_context_store[group_id])

    # Remove expired messages
    current_time = time.time()
    valid_messages = [
        msg for msg in messages
        if not msg.is_expired(_CONTEXT_TTL_SECONDS)
    ]

    # Return up to max_messages, ordered from oldest to newest
    return valid_messages[-max_messages:]


def get_context_as_text(group_id: str, max_messages: int = 5) -> str:
    """
    Get conversation context formatted as a text block for LLM prompt.

    Args:
        group_id: LINE group/room ID
        max_messages: Maximum number of messages to include

    Returns:
        Formatted conversation history string, or empty string if no context
    """
    messages = get_context(group_id, max_messages)

    if not messages:
        return ""

    # Format messages as conversation history
    lines = []
    for msg in messages:
        # Truncate user_id for display (first 4 chars)
        user_display = f"User_{msg.user_id[:4]}"

        # Format based on message type
        if msg.message_type == "image":
            lines.append(f"{user_display}: [發送了圖片]")
        elif msg.message_type == "sticker":
            lines.append(f"{user_display}: [發送了貼圖]")
        elif msg.message_type == "text":
            lines.append(f"{user_display}: {msg.text}")
        else:
            lines.append(f"{user_display}: [發送了{msg.message_type}]")

    return "\n".join(lines)


def clear_context(group_id: str) -> None:
    """
    Clear all conversation context for a specific group.

    Args:
        group_id: LINE group/room ID
    """
    if group_id in _context_store:
        _context_store[group_id].clear()


def clear_all_contexts() -> None:
    """Clear all conversation contexts for all groups."""
    _context_store.clear()


def get_stats() -> Dict[str, Any]:
    """
    Get statistics about the conversation context store.

    Returns:
        Dict with statistics including number of groups tracked and total messages
    """
    total_messages = sum(len(deque) for deque in _context_store.values())

    return {
        "groups_tracked": len(_context_store),
        "total_messages": total_messages,
        "max_messages_per_group": _MAX_MESSAGES_PER_GROUP,
        "ttl_seconds": _CONTEXT_TTL_SECONDS,
    }


def _cleanup_expired_messages() -> None:
    """
    Remove expired messages from all groups.

    Internal method called periodically during message additions.
    """
    current_time = time.time()
    groups_to_remove = []

    for group_id, messages in _context_store.items():
        # Filter out expired messages
        valid_messages = [
            msg for msg in messages
            if not msg.is_expired(_CONTEXT_TTL_SECONDS)
        ]

        if not valid_messages:
            # All messages expired, mark group for removal
            groups_to_remove.append(group_id)
        else:
            # Update deque with only valid messages
            _context_store[group_id] = deque(valid_messages, maxlen=_MAX_MESSAGES_PER_GROUP)

    # Remove groups with no valid messages
    for group_id in groups_to_remove:
        del _context_store[group_id]


def _log_current_context(group_id: str) -> None:
    """
    Log the current conversation context for a group.

    Args:
        group_id: LINE group/room ID
    """
    messages = get_context(group_id)
    if not messages:
        return

    # Format context for logging
    context_lines = []
    context_lines.append(f"📝 Current context for group {group_id[:8]}... ({len(messages)} messages):")

    for idx, msg in enumerate(messages, 1):
        user_display = f"User_{msg.user_id[:4]}" if not msg.user_id.startswith("BOT_") else "Bot"
        if msg.message_type == "text":
            # Truncate long messages for logging
            text_preview = msg.text[:50] + "..." if len(msg.text) > 50 else msg.text
            context_lines.append(f"  {idx}. {user_display}: {text_preview}")
        else:
            context_lines.append(f"  {idx}. {user_display}: [發送了{msg.message_type}]")

    logger.info("\n".join(context_lines))
