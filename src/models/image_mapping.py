"""
Image Mapping model for keyword-to-image associations.

Stores mappings from user keywords to image files in Google Drive
for the !img command functionality.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict
from datetime import datetime
import json
import re


# Allowed characters in keywords (alphanumeric + Chinese + common punctuation)
KEYWORD_PATTERN = re.compile(r'^[\w\u4e00-\u9fff\u3400-\u4dbf\-_]+$', re.UNICODE)

# Valid image extensions
VALID_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}


@dataclass
class ImageMapping:
    """
    Maps a keyword to an image file in Google Drive.
    
    Attributes:
        keyword: User-facing keyword (e.g., "架構圖")
        filename: Image filename in Google Drive (e.g., "architecture.png")
        file_id: Google Drive file ID for the image
        cached_path: Local cache path for downloaded image (optional)
        md5_checksum: MD5 hash for cache invalidation (optional)
    """
    
    keyword: str
    filename: str
    file_id: str
    cached_path: Optional[str] = None
    md5_checksum: Optional[str] = None
    
    def __post_init__(self):
        """Validate fields after initialization."""
        self.validate()
    
    def validate(self) -> None:
        """
        Validate mapping fields.
        
        Raises:
            ValueError: If validation fails
        """
        # Validate keyword
        if not self.keyword:
            raise ValueError("Keyword cannot be empty")
        
        if not KEYWORD_PATTERN.match(self.keyword):
            raise ValueError(
                f"Keyword '{self.keyword}' contains invalid characters. "
                "Only alphanumeric, Chinese characters, hyphens and underscores allowed."
            )
        
        # Validate filename extension
        ext = '.' + self.filename.split('.')[-1].lower() if '.' in self.filename else ''
        if ext not in VALID_IMAGE_EXTENSIONS:
            raise ValueError(
                f"Invalid image extension '{ext}'. "
                f"Allowed: {', '.join(VALID_IMAGE_EXTENSIONS)}"
            )
    
    @property
    def is_cached(self) -> bool:
        """Check if image is cached locally."""
        if not self.cached_path:
            return False
        from pathlib import Path
        return Path(self.cached_path).exists()
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "keyword": self.keyword,
            "filename": self.filename,
            "file_id": self.file_id,
        }


@dataclass
class ImageMappingConfig:
    """
    Configuration containing all image mappings.
    
    Loaded from image_map.json in Google Drive.
    
    Attributes:
        mappings: List of ImageMapping objects
        version: Config version number
        updated_at: When config was last updated
    """
    
    mappings: List[ImageMapping] = field(default_factory=list)
    version: int = 1
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    # Quick lookup by keyword
    _keyword_map: Dict[str, ImageMapping] = field(default_factory=dict, repr=False)
    
    def __post_init__(self):
        """Build keyword lookup map."""
        self._rebuild_lookup()
    
    def _rebuild_lookup(self) -> None:
        """Rebuild the keyword lookup dictionary."""
        self._keyword_map = {m.keyword.lower(): m for m in self.mappings}
    
    def get_by_keyword(self, keyword: str) -> Optional[ImageMapping]:
        """
        Find mapping by keyword (case-insensitive).
        
        Args:
            keyword: User-provided keyword
            
        Returns:
            ImageMapping if found, None otherwise
        """
        return self._keyword_map.get(keyword.lower())
    
    @property
    def keywords(self) -> List[str]:
        """Get list of all available keywords."""
        return [m.keyword for m in self.mappings]
    
    def add_mapping(self, mapping: ImageMapping) -> None:
        """Add a new mapping and update lookup."""
        self.mappings.append(mapping)
        self._keyword_map[mapping.keyword.lower()] = mapping
    
    @classmethod
    def from_json(cls, json_str: str) -> "ImageMappingConfig":
        """
        Parse config from JSON string.
        
        Expected format:
        {
            "mappings": [
                {"keyword": "foo", "filename": "foo.png", "file_id": "..."},
                ...
            ],
            "version": 1,
            "updated_at": "2026-01-07T12:00:00Z"
        }
        
        Args:
            json_str: JSON string
            
        Returns:
            ImageMappingConfig instance
            
        Raises:
            ValueError: If JSON is invalid
        """
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}")
        
        mappings = []
        for item in data.get("mappings", []):
            try:
                mapping = ImageMapping(
                    keyword=item["keyword"],
                    filename=item["filename"],
                    file_id=item["file_id"],
                )
                mappings.append(mapping)
            except (KeyError, ValueError) as e:
                # Skip invalid mappings but log warning
                import logging
                logging.warning(f"Skipping invalid mapping: {item} - {e}")
        
        version = data.get("version", 1)
        updated_at_str = data.get("updated_at")
        updated_at = datetime.utcnow()
        if updated_at_str:
            try:
                updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
            except ValueError:
                pass
        
        return cls(
            mappings=mappings,
            version=version,
            updated_at=updated_at,
        )
    
    def to_json(self) -> str:
        """Serialize config to JSON string."""
        return json.dumps({
            "mappings": [m.to_dict() for m in self.mappings],
            "version": self.version,
            "updated_at": self.updated_at.isoformat() + "Z",
        }, ensure_ascii=False, indent=2)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for logging."""
        return {
            "mapping_count": len(self.mappings),
            "keywords": self.keywords[:10],  # First 10 for brevity
            "version": self.version,
        }


# Empty default config
DEFAULT_IMAGE_CONFIG = ImageMappingConfig()
