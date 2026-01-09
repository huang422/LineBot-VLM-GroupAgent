"""
LLM Request model for queue processing.

Represents a queued inference job with all context needed
for Ollama API calls and LINE response handling.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from uuid import uuid4
import re


# LINE ID regex patterns
LINE_USER_ID_PATTERN = re.compile(r"^U[a-f0-9]{32}$")
LINE_GROUP_ID_PATTERN = re.compile(r"^C[a-f0-9]{32}$")
LINE_ROOM_ID_PATTERN = re.compile(r"^R[a-f0-9]{32}$")

# Validation constants
MAX_PROMPT_LENGTH = 4000


@dataclass
class LLMRequest:
    """
    Represents a queued LLM inference request.
    
    Attributes:
        request_id: Unique identifier for tracking (auto-generated UUID)
        user_id: LINE user ID who initiated the request
        group_id: LINE group/room ID where request originated
        prompt: User question text from !hej command
        system_prompt: System prompt for LLM behavior
        timestamp: When request was created
        reply_token: LINE reply token (valid for ~60s, optional)
        context_text: Quoted message text for reply-based interaction
        context_image_base64: Base64-encoded image for multimodal requests
        priority: Queue priority (0 = normal, higher = more urgent)
        max_retries: Maximum retry attempts for transient failures
        retry_count: Current retry attempt number
    """
    
    user_id: str
    group_id: str
    prompt: str
    system_prompt: str
    request_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)
    reply_token: Optional[str] = None
    context_text: Optional[str] = None
    context_image_base64: Optional[str] = None
    priority: int = 0
    max_retries: int = 1
    retry_count: int = 0
    
    def __post_init__(self):
        """Validate fields after initialization."""
        self.validate()
    
    def validate(self) -> None:
        """
        Validate all fields according to data-model.md rules.
        
        Raises:
            ValueError: If any validation fails
        """
        # Validate prompt
        if not self.prompt or not self.prompt.strip():
            raise ValueError("Prompt cannot be empty or whitespace")
        
        if len(self.prompt) > MAX_PROMPT_LENGTH:
            raise ValueError(f"Prompt exceeds maximum length of {MAX_PROMPT_LENGTH} characters")
        
        # Strip whitespace from prompt
        self.prompt = self.prompt.strip()
        
        # Validate user_id format (allow flexibility for different LINE ID types)
        if self.user_id and not self._is_valid_line_id(self.user_id, "user"):
            raise ValueError(f"Invalid LINE user ID format: {self.user_id[:8]}...")
        
        # Validate group_id format (can be group C or room R)
        if self.group_id and not self._is_valid_line_id(self.group_id, "group"):
            raise ValueError(f"Invalid LINE group/room ID format: {self.group_id[:8]}...")
    
    @staticmethod
    def _is_valid_line_id(id_value: str, id_type: str) -> bool:
        """Check if LINE ID matches expected format."""
        if not id_value:
            return False

        if id_type == "user":
            return bool(LINE_USER_ID_PATTERN.match(id_value))
        elif id_type == "group":
            # Accept both group (C), room (R), and user (U) IDs
            # User IDs are used as group_id for 1-on-1 chats
            return bool(LINE_GROUP_ID_PATTERN.match(id_value) or
                       LINE_ROOM_ID_PATTERN.match(id_value) or
                       LINE_USER_ID_PATTERN.match(id_value))
        return False
    
    @property
    def is_multimodal(self) -> bool:
        """Check if this request includes image content."""
        return self.context_image_base64 is not None
    
    @property
    def has_context(self) -> bool:
        """Check if this request has any context (text or image)."""
        return self.context_text is not None or self.context_image_base64 is not None
    
    @property
    def can_retry(self) -> bool:
        """Check if this request can be retried."""
        return self.retry_count < self.max_retries
    
    def increment_retry(self) -> None:
        """Increment retry counter for failed attempts."""
        self.retry_count += 1
    
    @property
    def age_seconds(self) -> float:
        """Get request age in seconds."""
        return (datetime.utcnow() - self.timestamp).total_seconds()
    
    def to_dict(self) -> dict:
        """Convert to dictionary for logging/debugging."""
        return {
            "request_id": self.request_id,
            "user_id": f"{self.user_id[:4]}...{self.user_id[-4:]}" if self.user_id else None,
            "group_id": f"{self.group_id[:4]}...{self.group_id[-4:]}" if self.group_id else None,
            "prompt_length": len(self.prompt),
            "has_context_text": self.context_text is not None,
            "has_context_image": self.context_image_base64 is not None,
            "timestamp": self.timestamp.isoformat(),
            "priority": self.priority,
            "retry_count": self.retry_count,
        }
