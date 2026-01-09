"""
Cached Asset model for Google Drive file caching.

Stores metadata about locally cached files from Google Drive
with timestamps for cache invalidation and LRU eviction.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class CachedAsset:
    """
    Represents a locally cached file from Google Drive.
    
    Attributes:
        file_id: Google Drive file ID
        filename: Original filename from Drive
        local_path: Path to cached file on local disk
        md5_checksum: MD5 hash from Google Drive for validation
        size_bytes: File size for cache eviction calculations
        cached_at: When file was downloaded
        last_accessed: For LRU eviction policy
        content_type: MIME type (e.g., "text/markdown", "image/png")
    """
    
    file_id: str
    filename: str
    local_path: str
    md5_checksum: str
    size_bytes: int
    cached_at: datetime = field(default_factory=datetime.utcnow)
    last_accessed: datetime = field(default_factory=datetime.utcnow)
    content_type: str = "application/octet-stream"
    
    def __post_init__(self):
        """Validate fields after initialization."""
        if self.size_bytes < 0:
            raise ValueError("size_bytes must be non-negative")
    
    @property
    def exists(self) -> bool:
        """Check if cached file still exists on disk."""
        return Path(self.local_path).exists()
    
    @property
    def age_seconds(self) -> float:
        """Get cache age in seconds."""
        return (datetime.utcnow() - self.cached_at).total_seconds()
    
    @property
    def idle_seconds(self) -> float:
        """Get seconds since last access (for LRU)."""
        return (datetime.utcnow() - self.last_accessed).total_seconds()
    
    def touch(self) -> None:
        """Update last_accessed timestamp."""
        self.last_accessed = datetime.utcnow()
    
    def needs_revalidation(self, new_checksum: str) -> bool:
        """
        Check if file needs re-downloading based on checksum.
        
        Args:
            new_checksum: MD5 checksum from Google Drive
            
        Returns:
            True if checksums differ (file changed)
        """
        return self.md5_checksum != new_checksum
    
    def read_bytes(self) -> Optional[bytes]:
        """
        Read cached file content.
        
        Returns:
            File content as bytes, or None if file not found
        """
        try:
            self.touch()
            return Path(self.local_path).read_bytes()
        except FileNotFoundError:
            return None
    
    def read_text(self, encoding: str = "utf-8") -> Optional[str]:
        """
        Read cached file as text.
        
        Args:
            encoding: Text encoding (default UTF-8)
            
        Returns:
            File content as string, or None if file not found
        """
        try:
            self.touch()
            return Path(self.local_path).read_text(encoding=encoding)
        except (FileNotFoundError, UnicodeDecodeError):
            return None
    
    def delete(self) -> bool:
        """
        Delete cached file from disk.
        
        Returns:
            True if file was deleted, False if not found
        """
        try:
            Path(self.local_path).unlink()
            return True
        except FileNotFoundError:
            return False
    
    def to_dict(self) -> dict:
        """Convert to dictionary for logging/debugging."""
        return {
            "file_id": self.file_id,
            "filename": self.filename,
            "size_bytes": self.size_bytes,
            "md5_checksum": self.md5_checksum[:8] + "..." if self.md5_checksum else None,
            "cached_at": self.cached_at.isoformat(),
            "age_seconds": int(self.age_seconds),
            "exists": self.exists,
        }
