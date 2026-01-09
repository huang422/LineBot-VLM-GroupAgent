"""
Command Handler for parsing and routing LINE messages.

Detects command prefixes (!hej, !img, !reload) and routes
to appropriate handlers. Ignores non-command messages.
"""

from typing import Optional, Tuple, Dict, Any
from dataclasses import dataclass
from enum import Enum

from src.utils.logger import get_logger
from src.utils.validators import sanitize_prompt, detect_prompt_injection

logger = get_logger("handlers.command")


class CommandType(Enum):
    """Supported command types."""
    HEJ = "hej"      # LLM inference
    IMG = "img"      # Image retrieval
    RELOAD = "reload"  # Force Drive sync
    UNKNOWN = "unknown"
    NONE = "none"    # Not a command


@dataclass
class ParsedCommand:
    """Parsed command data."""
    command_type: CommandType
    argument: str
    raw_text: str
    is_reply: bool = False
    quoted_message_id: Optional[str] = None
    quoted_message_type: Optional[str] = None
    quoted_message_text: Optional[str] = None
    
    @property
    def is_valid(self) -> bool:
        """Check if this is a valid command."""
        return self.command_type not in (CommandType.UNKNOWN, CommandType.NONE)
    
    @property
    def has_quoted_content(self) -> bool:
        """Check if there's quoted content to process."""
        return self.is_reply and (
            self.quoted_message_text is not None or 
            self.quoted_message_type == "image"
        )


# Command prefixes (case-insensitive matching)
COMMAND_PREFIXES = {
    "!hej": CommandType.HEJ,
    "!img": CommandType.IMG,
    "!reload": CommandType.RELOAD,
}


def parse_command(text: str) -> Tuple[CommandType, str]:
    """
    Parse command prefix and extract argument.
    
    Args:
        text: Raw message text
        
    Returns:
        Tuple of (CommandType, argument string)
    """
    if not text:
        return (CommandType.NONE, "")
    
    text = text.strip()
    text_lower = text.lower()
    
    for prefix, cmd_type in COMMAND_PREFIXES.items():
        if text_lower.startswith(prefix):
            # Extract argument after prefix
            argument = text[len(prefix):].strip()
            return (cmd_type, argument)
    
    # Check if starts with ! but unknown command
    if text.startswith("!"):
        # Extract the command word
        parts = text.split(maxsplit=1)
        logger.debug(f"Unknown command: {parts[0]}")
        return (CommandType.UNKNOWN, "")
    
    return (CommandType.NONE, "")


def parse_webhook_message(event: Dict[str, Any]) -> Optional[ParsedCommand]:
    """
    Parse a LINE webhook message event into a command.
    
    Args:
        event: LINE webhook event dictionary
        
    Returns:
        ParsedCommand if message contains a command, None otherwise
    """
    # Only handle message events
    if event.get("type") != "message":
        return None
    
    message = event.get("message", {})
    message_type = message.get("type")
    
    # Only process text messages for commands
    if message_type != "text":
        return None
    
    text = message.get("text", "")
    command_type, argument = parse_command(text)
    
    # Ignore non-commands
    if command_type == CommandType.NONE:
        return None
    
    # Check for reply/quote
    is_reply = False
    quoted_message_id = None
    quoted_message_type = None
    quoted_message_text = None

    # LINE uses quotedMessageId when user replies to a message
    if "quotedMessageId" in message:
        is_reply = True
        quoted_message_id = message["quotedMessageId"]
        logger.debug(f"Detected quoted message: {quoted_message_id}")
    
    # Sanitize the argument for !hej commands
    if command_type == CommandType.HEJ:
        argument = sanitize_prompt(argument)
        
        # Check for prompt injection
        if injection_pattern := detect_prompt_injection(argument):
            logger.warning(
                f"Potential prompt injection detected",
                extra={"pattern": injection_pattern[:30]}
            )
            # Still process but log the attempt
    
    return ParsedCommand(
        command_type=command_type,
        argument=argument,
        raw_text=text,
        is_reply=is_reply,
        quoted_message_id=quoted_message_id,
        quoted_message_type=quoted_message_type,
        quoted_message_text=quoted_message_text,
    )


def extract_event_context(event: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """
    Extract user/group context from webhook event.

    Args:
        event: LINE webhook event

    Returns:
        Dictionary with user_id, group_id, reply_token
    """
    source = event.get("source", {})

    # Extract group_id or user_id as fallback
    # For 1-on-1 chats, we use user_id as the target for push messages
    group_id = source.get("groupId") or source.get("roomId") or source.get("userId")

    return {
        "user_id": source.get("userId"),
        "group_id": group_id,
        "reply_token": event.get("replyToken"),
        "message_id": event.get("message", {}).get("id"),
    }
