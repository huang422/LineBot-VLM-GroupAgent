# Data Model: LINE Bot with Local Ollama VLM Integration

**Feature**: [spec.md](./spec.md) | **Phase**: 1 (Design) | **Date**: 2026-01-07

## Purpose

This document defines the key entities, their attributes, relationships, and validation rules for the LINE Bot system. These models represent the core data structures used throughout the application.

## Entity Definitions

### 1. LLMRequest

**Purpose**: Represents a queued inference job submitted to the async processing queue.

**Attributes**:
- `request_id` (str, UUID): Unique identifier for tracking
- `user_id` (str): LINE user ID who initiated the request
- `group_id` (str): LINE group ID where request originated
- `reply_token` (str, optional): LINE reply token (valid for 60s)
- `prompt` (str): User question text (from `!hej <question>`)
- `system_prompt` (str): System prompt loaded from Google Drive
- `context_text` (str, optional): Quoted message text (if reply-based interaction)
- `context_image_base64` (str, optional): Base64-encoded image (if reply-based interaction)
- `timestamp` (datetime): When request was created
- `priority` (int, default=0): Future enhancement for queue prioritization
- `max_retries` (int, default=1): Retry limit for transient failures

**Validation Rules**:
- `prompt` must not be empty after stripping whitespace
- `prompt` length must not exceed 4000 characters (prevent context overflow)
- Either `context_text` or `context_image_base64` or both may be present
- `user_id` and `group_id` must match LINE ID format (U[a-f0-9]{32}, C[a-f0-9]{32})

**Relationships**:
- Created by `CommandHandler` when parsing `!hej` commands
- Consumed by `QueueService` worker
- References `PromptConfig` for system prompt

**Example**:
```python
LLMRequest(
    request_id="550e8400-e29b-41d4-a716-446655440000",
    user_id="U4af4980629...",
    group_id="Ca56f94637c...",
    reply_token="b60d432864f44d079f6d8efe86cf404b",
    prompt="What's in this image?",
    system_prompt="You are a helpful assistant analyzing images.",
    context_text=None,
    context_image_base64="iVBORw0KGgoAAAANSUhEUgAAAAUA...",
    timestamp=datetime(2026, 1, 7, 12, 34, 56),
    priority=0,
    max_retries=1
)
```

---

### 2. PromptConfig

**Purpose**: The system prompt configuration loaded from Google Drive that defines bot personality and behavior.

**Attributes**:
- `content` (str): The actual system prompt text
- `file_id` (str): Google Drive file ID for `system_prompt.md`
- `modified_time` (datetime): Last modification timestamp from Drive
- `md5_checksum` (str): MD5 hash for change detection
- `cached_at` (datetime): When this version was cached locally
- `version` (int, default=1): Incremental version number for tracking updates

**Validation Rules**:
- `content` must not be empty
- `content` length should not exceed 2000 characters (recommended for context efficiency)
- `md5_checksum` must be valid MD5 hash (32 hex characters)

**Relationships**:
- Loaded by `DriveService` during startup and periodic sync
- Referenced by `LLMRequest` when constructing prompts
- Updated when Drive polling detects changes

**Example**:
```python
PromptConfig(
    content="You are a helpful assistant in a LINE group chat. Respond concisely in Traditional Chinese or English based on the user's language.",
    file_id="1a2b3c4d5e6f7g8h9i0j",
    modified_time=datetime(2026, 1, 7, 10, 0, 0),
    md5_checksum="5d41402abc4b2a76b9719d911017c592",
    cached_at=datetime(2026, 1, 7, 10, 0, 5),
    version=3
)
```

---

### 3. ImageMapping

**Purpose**: Keyword-to-filename associations for `!img` command, loaded from `image_map.json`.

**Attributes**:
- `keyword` (str): User-facing keyword (e.g., "架構圖")
- `filename` (str): Image filename in Google Drive (e.g., "architecture.png")
- `file_id` (str): Google Drive file ID for the image asset
- `cached_path` (str): Local cache path for downloaded image binary
- `md5_checksum` (str): MD5 hash for cache invalidation

**Validation Rules**:
- `keyword` must not contain whitespace or special characters (alphanumeric + Chinese characters only)
- `filename` must end with valid image extension (.png, .jpg, .jpeg, .webp)
- `file_id` must be valid Google Drive file ID format

**Relationships**:
- Loaded by `DriveService` from `image_map.json`
- Used by `ImgHandler` to resolve keyword requests
- Images cached by `ImageService` on demand

**Example**:
```python
ImageMapping(
    keyword="架構圖",
    filename="architecture.png",
    file_id="1x2y3z4a5b6c7d8e9f0g",
    cached_path="/tmp/linebot_cache/images/architecture.png",
    md5_checksum="098f6bcd4621d373cade4e832627b4f6"
)
```

**Note**: Images are sent to LINE using binary data from cached file, not via URL. No static file server needed.

**Collection Structure** (`image_map.json`):
```json
{
  "mappings": [
    {
      "keyword": "架構圖",
      "filename": "architecture.png",
      "file_id": "1x2y3z4a5b6c7d8e9f0g"
    },
    {
      "keyword": "meme",
      "filename": "funny_cat.jpg",
      "file_id": "2a3b4c5d6e7f8g9h0i1j"
    }
  ],
  "version": 2,
  "updated_at": "2026-01-07T10:00:00Z"
}
```

---

### 4. CachedAsset

**Purpose**: Represents locally cached files from Google Drive (prompts, config, images) with metadata for invalidation.

**Attributes**:
- `file_id` (str): Google Drive file ID
- `filename` (str): Original filename
- `local_path` (str): Path to cached file on local disk
- `md5_checksum` (str): MD5 hash from Google Drive
- `size_bytes` (int): File size for cache eviction calculations
- `cached_at` (datetime): When file was downloaded
- `last_accessed` (datetime): For LRU eviction policy
- `content_type` (str): MIME type (e.g., "text/markdown", "image/png")

**Validation Rules**:
- `local_path` must exist and be readable (checked on access)
- `md5_checksum` matches actual file checksum (verified periodically)
- `size_bytes` must be positive integer

**Relationships**:
- Managed by `DriveService` caching layer
- Referenced by `PromptConfig` and `ImageMapping`
- Evicted by LRU policy when cache exceeds limit

**Example**:
```python
CachedAsset(
    file_id="1a2b3c4d5e6f7g8h9i0j",
    filename="system_prompt.md",
    local_path="/tmp/drive_cache/system_prompt.md",
    md5_checksum="5d41402abc4b2a76b9719d911017c592",
    size_bytes=1024,
    cached_at=datetime(2026, 1, 7, 10, 0, 5),
    last_accessed=datetime(2026, 1, 7, 12, 34, 56),
    content_type="text/markdown"
)
```

---

### 5. RateLimitTracker

**Purpose**: Tracks per-user request counts for enforcing 30 requests/minute limit.

**Attributes**:
- `user_id` (str): LINE user ID
- `request_timestamps` (list[datetime]): Sliding window of request times
- `window_seconds` (int, default=60): Time window for rate limiting
- `max_requests` (int, default=30): Maximum requests per window

**Validation Rules**:
- `request_timestamps` automatically pruned (remove timestamps older than window)
- `user_id` must be valid LINE user ID format

**Methods**:
- `is_allowed() -> tuple[bool, int]`: Check if request allowed, return (allowed, seconds_until_reset)
- `record_request()`: Add current timestamp to tracking list
- `reset()`: Clear all timestamps (for testing or admin override)

**Relationships**:
- Managed by `RateLimitService`
- Checked before adding `LLMRequest` to queue
- In-memory storage (Redis optional for multi-instance)

**Example**:
```python
RateLimitTracker(
    user_id="U4af4980629...",
    request_timestamps=[
        datetime(2026, 1, 7, 12, 34, 10),
        datetime(2026, 1, 7, 12, 34, 25),
        datetime(2026, 1, 7, 12, 34, 40),
        # ... up to 30 timestamps in past 60 seconds
    ],
    window_seconds=60,
    max_requests=30
)
```

---

### 6. AdminContact

**Purpose**: Configured LINE user IDs designated to receive critical system alerts.

**Attributes**:
- `user_id` (str): LINE user ID of administrator
- `name` (str): Human-readable name for logging
- `alert_level` (str, enum): Minimum alert severity to notify ("critical", "warning", "info")
- `active` (bool, default=True): Whether to send notifications to this admin

**Validation Rules**:
- `user_id` must be valid LINE user ID format
- `alert_level` must be one of: "critical", "warning", "info"

**Relationships**:
- Loaded from configuration (environment variables or config file)
- Used by error handling logic to send push notifications
- Multiple admins can be configured (FR-046, FR-047)

**Example**:
```python
AdminContact(
    user_id="U1234567890abcdef1234567890abcdef",
    name="Tom (主要管理員)",
    alert_level="warning",
    active=True
)
```

**Configuration Format** (`.env` or config):
```bash
ADMIN_USER_IDS=U1234567890abcdef1234567890abcdef,U9876543210fedcba9876543210fedcba
ADMIN_ALERT_LEVEL=warning
```

---

## Entity Relationships Diagram

```
┌─────────────────┐
│  PromptConfig   │
│  (Drive Sync)   │
└────────┬────────┘
         │
         │ references
         ▼
┌─────────────────┐       ┌──────────────────┐
│   LLMRequest    │──────▶│  RateLimitTracker│
│  (Queue Item)   │checks │  (Per-User)      │
└────────┬────────┘       └──────────────────┘
         │
         │ processed by
         ▼
┌─────────────────┐       ┌──────────────────┐
│  QueueService   │──────▶│  OllamaService   │
│  (Worker)       │calls  │  (LLM API)       │
└─────────────────┘       └──────────────────┘

┌─────────────────┐       ┌──────────────────┐
│  ImageMapping   │──────▶│  CachedAsset     │
│  (Keyword Map)  │refs   │  (Local Cache)   │
└────────┬────────┘       └──────────────────┘
         │
         │ used by
         ▼
┌─────────────────┐
│   ImgHandler    │
│  (!img cmd)     │
└─────────────────┘

┌─────────────────┐
│  AdminContact   │
│  (Alert Targets)│
└────────┬────────┘
         │
         │ notified by
         ▼
┌─────────────────┐
│  ErrorHandler   │
│  (Monitoring)   │
└─────────────────┘
```

## Data Flow Example: `!hej` Command with Image Reply

1. **User replies to image message with `!hej What's in this?`**
2. **LINE webhook** → `LineService` receives event
3. **CommandHandler** detects `!hej` command, extracts:
   - `prompt`: "What's in this?"
   - `quoted_message_id`: "325700"
4. **ImageService** downloads image from LINE Content API → BytesIO → resize → base64
5. **RateLimitService** checks `RateLimitTracker[user_id]` → allowed (count: 15/30)
6. **CommandHandler** creates `LLMRequest`:
   - `prompt`: "What's in this?"
   - `system_prompt`: from `PromptConfig`
   - `context_image_base64`: base64 string
7. **QueueService** adds to `asyncio.Queue` (current size: 3/10)
8. **Worker** dequeues request, acquires `Semaphore(1)`, calls `OllamaService`
9. **OllamaService** sends multimodal request to Ollama API
10. **LineService** sends response back to group using `reply_token`
11. **RateLimitTracker** updated with new timestamp

## Validation and Constraints

### Input Validation
- All user-provided text (prompts, keywords) sanitized to prevent injection
- LINE signature validation mandatory (FR-039)
- JSON schema validation for `image_map.json` (FR-026)

### Data Retention
- `LLMRequest` objects: Discarded after processing (no persistence)
- `CachedAsset`: Retained until LRU eviction or manual cache clear
- `RateLimitTracker`: Timestamps pruned after 60 seconds
- `PromptConfig`: Retained indefinitely (overwritten on updates)

### Privacy Compliance
- User images NEVER written to disk (in-memory BytesIO only)
- Only Google Drive static assets cached locally
- No conversation history stored (stateless bot)

## Implementation Notes

### Dataclass Examples

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class LLMRequest:
    request_id: str
    user_id: str
    group_id: str
    prompt: str
    system_prompt: str
    timestamp: datetime
    reply_token: Optional[str] = None
    context_text: Optional[str] = None
    context_image_base64: Optional[str] = None
    priority: int = 0
    max_retries: int = 1

@dataclass
class PromptConfig:
    content: str
    file_id: str
    modified_time: datetime
    md5_checksum: str
    cached_at: datetime
    version: int = 1
```

### Pydantic Models (Alternative)

```python
from pydantic import BaseModel, Field, validator
from datetime import datetime

class LLMRequest(BaseModel):
    request_id: str
    user_id: str = Field(..., regex=r'^U[a-f0-9]{32}$')
    group_id: str = Field(..., regex=r'^C[a-f0-9]{32}$')
    prompt: str = Field(..., min_length=1, max_length=4000)
    system_prompt: str
    timestamp: datetime
    reply_token: Optional[str] = None
    context_text: Optional[str] = None
    context_image_base64: Optional[str] = None
    priority: int = 0
    max_retries: int = 1

    @validator('prompt')
    def prompt_not_empty(cls, v):
        if not v.strip():
            raise ValueError('Prompt cannot be empty or whitespace')
        return v.strip()
```

## Next Steps

✅ **Phase 1 Data Models Complete** → Proceed to Contracts and Quickstart
