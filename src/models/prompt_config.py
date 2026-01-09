"""
Prompt Configuration model for Google Drive integration.

Stores system prompt content with caching metadata for
efficient change detection and reload handling.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class PromptConfig:
    """
    System prompt configuration loaded from Google Drive.
    
    Attributes:
        content: The actual system prompt text
        file_id: Google Drive file ID for system_prompt.md
        modified_time: Last modification timestamp from Drive
        md5_checksum: MD5 hash for change detection
        cached_at: When this version was cached locally
        version: Incremental version number for tracking updates
    """
    
    content: str
    file_id: Optional[str] = None
    modified_time: Optional[datetime] = None
    md5_checksum: Optional[str] = None
    cached_at: datetime = field(default_factory=datetime.utcnow)
    version: int = 1
    
    def __post_init__(self):
        """Validate content after initialization."""
        if not self.content or not self.content.strip():
            raise ValueError("Prompt content cannot be empty")
        self.content = self.content.strip()
    
    @property
    def content_length(self) -> int:
        """Get content length in characters."""
        return len(self.content)
    
    @property
    def age_seconds(self) -> float:
        """Get cache age in seconds."""
        return (datetime.utcnow() - self.cached_at).total_seconds()
    
    def is_stale(self, max_age_seconds: float = 60.0) -> bool:
        """
        Check if cached prompt might be stale.
        
        Args:
            max_age_seconds: Maximum age before considering stale
            
        Returns:
            True if cache is older than max_age_seconds
        """
        return self.age_seconds > max_age_seconds
    
    def needs_update(self, new_checksum: str) -> bool:
        """
        Check if prompt needs to be updated based on checksum.
        
        Args:
            new_checksum: MD5 checksum from Google Drive
            
        Returns:
            True if checksums differ (content changed)
        """
        if not self.md5_checksum:
            return True
        return self.md5_checksum != new_checksum
    
    def update_from(
        self,
        content: str,
        file_id: str,
        modified_time: datetime,
        md5_checksum: str
    ) -> "PromptConfig":
        """
        Create updated config with new content.
        
        Args:
            content: New prompt content
            file_id: Google Drive file ID
            modified_time: File modification time
            md5_checksum: New MD5 checksum
            
        Returns:
            New PromptConfig with incremented version
        """
        return PromptConfig(
            content=content,
            file_id=file_id,
            modified_time=modified_time,
            md5_checksum=md5_checksum,
            cached_at=datetime.utcnow(),
            version=self.version + 1,
        )
    
    def to_dict(self) -> dict:
        """Convert to dictionary for logging/debugging."""
        return {
            "content_length": self.content_length,
            "file_id": self.file_id,
            "modified_time": self.modified_time.isoformat() if self.modified_time else None,
            "md5_checksum": self.md5_checksum[:8] + "..." if self.md5_checksum else None,
            "cached_at": self.cached_at.isoformat(),
            "version": self.version,
        }


# Default prompt when Google Drive is not configured
DEFAULT_PROMPT_CONFIG = PromptConfig(
    content="""You are a helpful AI assistant in a LINE group chat.
Respond concisely and helpfully in the same language the user uses.
If analyzing images, describe what you see clearly and answer any questions about the content.
Be friendly but professional.""",
    version=0,
)
