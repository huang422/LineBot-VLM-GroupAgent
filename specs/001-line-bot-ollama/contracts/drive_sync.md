# Google Drive Synchronization Contract

**Feature**: [spec.md](../spec.md) | **Phase**: 1 (Design) | **Date**: 2026-01-07

## Purpose

This contract defines the integration between our LINE Bot and Google Drive for collaborative prompt and asset management. It specifies the polling strategy, caching mechanism, change detection, and file structure requirements.

## Service Configuration

### Authentication
- **Method**: Service Account credentials
- **Scopes**: `https://www.googleapis.com/auth/drive.readonly`
- **Credentials File**: `service_account_key.json` (stored securely, not in git)
- **API Version**: v3

### Google Drive Structure

**Required Folder Structure**:
```
LINE Bot Config/  (Shared folder, service account has Viewer access)
├── system_prompt.md       # System prompt for LLM
├── image_map.json         # Keyword-to-image mappings
└── images/                # Static image assets
    ├── architecture.png
    ├── guide.jpg
    └── meme.webp
```

**Folder ID**: Retrieved via API or manually configured in `.env`
```bash
GOOGLE_DRIVE_FOLDER_ID=1aBcDeFgHiJkLmNoPqRsTuVwXyZ
```

---

## File Specifications

### 1. system_prompt.md

**Purpose**: Define bot personality and behavior for LLM inference

**Format**: Plain text Markdown (no special syntax required)

**Example Content**:
```markdown
You are a helpful assistant in a LINE group chat.

Guidelines:
- Respond concisely (1-3 sentences preferred)
- Use Traditional Chinese when user writes in Chinese
- Use English when user writes in English
- Be friendly and conversational
- If you don't know something, admit it honestly

Special instructions:
- For image analysis, describe key visual elements clearly
- Avoid making assumptions beyond what's visible in images
```

**Validation Rules**:
- Must be valid UTF-8 text
- Recommended max length: 2000 characters (to preserve context window)
- No required structure (free-form text)

**Google Drive Metadata**:
- File ID: Retrieved via API
- Modified Time: ISO 8601 timestamp
- MD5 Checksum: Used for change detection

---

### 2. image_map.json

**Purpose**: Map keywords to image filenames for `!img` command

**Format**: JSON with strict schema

**Example Content**:
```json
{
  "version": 2,
  "updated_at": "2026-01-07T10:00:00Z",
  "mappings": [
    {
      "keyword": "架構圖",
      "filename": "architecture.png",
      "description": "系統架構圖"
    },
    {
      "keyword": "guide",
      "filename": "guide.jpg",
      "description": "User guide image"
    },
    {
      "keyword": "meme",
      "filename": "meme.webp",
      "description": "Funny cat meme"
    }
  ]
}
```

**Schema Definition**:
```json
{
  "type": "object",
  "required": ["version", "mappings"],
  "properties": {
    "version": {
      "type": "integer",
      "description": "Config version for tracking updates"
    },
    "updated_at": {
      "type": "string",
      "format": "date-time",
      "description": "ISO 8601 timestamp"
    },
    "mappings": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["keyword", "filename"],
        "properties": {
          "keyword": {
            "type": "string",
            "pattern": "^[a-zA-Z0-9\\u4e00-\\u9fff]+$",
            "description": "Alphanumeric + Chinese characters only"
          },
          "filename": {
            "type": "string",
            "pattern": "\\.(png|jpg|jpeg|webp)$",
            "description": "Must be valid image filename"
          },
          "description": {
            "type": "string",
            "description": "Optional human-readable description"
          }
        }
      }
    }
  }
}
```

**Validation Rules** (FR-026):
- Must be valid JSON
- Must conform to schema above
- Keywords must be unique (no duplicates)
- Filenames must reference files that exist in `images/` folder
- If validation fails, log error and continue using previous valid config

---

### 3. Image Assets (images/ folder)

**Purpose**: Images sent to LINE via `!img` command using binary data upload

**Supported Formats**:
- PNG (`.png`)
- JPEG (`.jpg`, `.jpeg`)
- WebP (`.webp`)

**Size Limits**:
- Recommended max: 5MB per image
- LINE API limit: 10MB per image message

**Caching Strategy**:
- Images downloaded on demand (first `!img` request)
- Cached locally with MD5 checksum at `/tmp/linebot_cache/images/`
- Invalidated when Drive file modified time changes
- Sent to LINE using binary upload (no static file server, no public URLs)

---

## Polling Strategy

### Change Detection Flow

**Initialization** (on bot startup):
```python
# Step 1: Get initial page token
response = service.changes().getStartPageToken().execute()
page_token = response['startPageToken']

# Step 2: Download initial config files
download_file('system_prompt.md')
download_file('image_map.json')
```

**Polling Loop** (every 30-60 seconds):
```python
while True:
    # Step 1: Check for changes since last page token
    response = service.changes().list(
        pageToken=page_token,
        spaces='drive',
        fields='nextPageToken,newStartPageToken,changes(fileId,file(name,modifiedTime,md5Checksum))',
        includeRemoved=False  # Ignore deleted files
    ).execute()

    # Step 2: Process changes
    for change in response.get('changes', []):
        file_info = change['file']
        if file_info['name'] in ['system_prompt.md', 'image_map.json']:
            handle_config_change(file_info)
        elif file_info['name'].startswith('images/'):
            handle_image_change(file_info)

    # Step 3: Update page token for next iteration
    page_token = response.get('nextPageToken') or response.get('newStartPageToken')

    # Step 4: Wait before next poll
    await asyncio.sleep(30)  # 30 second interval
```

**Change Detection Logic**:
```python
def handle_config_change(file_info: dict):
    """Handle changes to config files"""
    file_id = file_info['fileId']
    filename = file_info['name']
    new_md5 = file_info['md5Checksum']

    # Check if file actually changed
    cached = get_cached_asset(file_id)
    if cached and cached.md5_checksum == new_md5:
        logger.info(f"{filename} unchanged (MD5 match)")
        return

    # Download updated file
    logger.info(f"{filename} changed, downloading...")
    content = download_file_content(file_id)

    # Validate before applying
    if filename == 'image_map.json':
        if not validate_image_map_json(content):
            logger.error("Invalid image_map.json, keeping previous version")
            return

    # Update cache and apply changes
    update_cache(file_id, content, new_md5)
    apply_config_update(filename, content)
    logger.info(f"{filename} updated successfully (version {get_version()})")
```

---

## API Integration Examples

### Authentication Setup

```python
from google.oauth2 import service_account
from googleapiclient.discovery import build
import os

def init_drive_service():
    """Initialize Google Drive API client"""
    SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
    SERVICE_ACCOUNT_FILE = os.getenv('GOOGLE_SERVICE_ACCOUNT_FILE', 'service_account_key.json')

    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )

    service = build('drive', 'v3', credentials=credentials)
    return service
```

### File Download

```python
from googleapiclient.http import MediaIoBaseDownload
import io

def download_file_content(service, file_id: str) -> bytes:
    """Download file content from Google Drive"""
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)

    done = False
    while not done:
        status, done = downloader.next_chunk()
        if status:
            logger.debug(f"Download progress: {int(status.progress() * 100)}%")

    fh.seek(0)
    return fh.read()
```

### Find Files in Folder

```python
def find_files_in_folder(service, folder_id: str) -> dict:
    """List all files in specified folder"""
    query = f"'{folder_id}' in parents and trashed=false"
    results = service.files().list(
        q=query,
        spaces='drive',
        fields='files(id, name, modifiedTime, md5Checksum, mimeType)',
        pageSize=100
    ).execute()

    files = results.get('files', [])
    return {file['name']: file for file in files}
```

---

## Caching Mechanism

### Local Cache Structure

```
/tmp/linebot_cache/
├── system_prompt.md         # Cached config files
├── image_map.json
├── images/
│   ├── architecture.png     # Cached image assets
│   ├── guide.jpg
│   └── meme.webp
└── .cache_metadata.json     # Metadata for cache invalidation
```

### Cache Metadata Format

```json
{
  "version": 1,
  "last_sync": "2026-01-07T12:34:56Z",
  "files": {
    "system_prompt.md": {
      "file_id": "1a2b3c4d5e6f7g8h9i0j",
      "md5_checksum": "5d41402abc4b2a76b9719d911017c592",
      "modified_time": "2026-01-07T10:00:00Z",
      "cached_at": "2026-01-07T10:00:05Z",
      "size_bytes": 1024
    },
    "image_map.json": {
      "file_id": "2b3c4d5e6f7g8h9i0j1k",
      "md5_checksum": "098f6bcd4621d373cade4e832627b4f6",
      "modified_time": "2026-01-07T09:30:00Z",
      "cached_at": "2026-01-07T09:30:02Z",
      "size_bytes": 512
    }
  }
}
```

### Cache Invalidation

**Triggers for Re-download**:
1. MD5 checksum mismatch (file content changed)
2. Modified time changed (Google Drive metadata)
3. Cache file missing locally (deleted or corrupted)
4. Manual `!reload` command (bypass cache entirely)

**LRU Eviction** (if cache exceeds 100MB):
```python
def evict_least_recently_used(cache_dir: str, max_size_mb: int = 100):
    """Remove least recently accessed files to stay under size limit"""
    files = []
    total_size = 0

    for root, dirs, filenames in os.walk(cache_dir):
        for filename in filenames:
            path = os.path.join(root, filename)
            stat = os.stat(path)
            files.append((path, stat.st_atime, stat.st_size))
            total_size += stat.st_size

    if total_size < max_size_mb * 1024 * 1024:
        return  # Under limit

    # Sort by access time (oldest first)
    files.sort(key=lambda x: x[1])

    # Remove files until under limit
    for path, atime, size in files:
        if total_size < max_size_mb * 1024 * 1024:
            break
        os.remove(path)
        total_size -= size
        logger.info(f"Evicted {path} (LRU policy)")
```

---

## Error Handling

### Scenario 1: Google Drive API Unavailable

**Trigger**: Network issue, API outage, quota exceeded

**Bot Behavior**:
- Continue using cached config (FR-045)
- Log error with retry attempt count
- Send admin alert if unavailable for >5 minutes (FR-046)
- Do NOT crash or stop processing messages

```python
try:
    check_for_changes()
except (HttpError, ConnectionError) as e:
    logger.error(f"Drive API error: {e}")
    if consecutive_failures > 10:  # 5 minutes at 30s intervals
        send_admin_alert(f"Drive sync failing for 5+ minutes: {e}")
```

### Scenario 2: Authentication Expired

**Trigger**: Service account credentials revoked or expired

**Bot Behavior**:
- Log critical error
- Send admin alert immediately (FR-046)
- Continue with cached config
- Stop attempting sync until credentials refreshed

### Scenario 3: Invalid JSON in image_map.json

**Trigger**: User edits file with syntax error

**Bot Behavior**:
- Validate JSON schema (FR-026)
- Log warning with line number and error details
- Keep previous valid config loaded
- Optionally send admin notification (non-critical)

```python
def validate_and_load_image_map(content: str) -> dict:
    """Validate image_map.json before applying"""
    try:
        data = json.loads(content)
        # Validate schema
        validate(instance=data, schema=IMAGE_MAP_SCHEMA)
        return data
    except json.JSONDecodeError as e:
        logger.warning(f"Invalid JSON: {e}")
        return None  # Keep previous config
    except ValidationError as e:
        logger.warning(f"Schema validation failed: {e}")
        return None
```

### Scenario 4: Referenced Image File Missing

**Trigger**: `image_map.json` references image that doesn't exist in `images/`

**Bot Behavior**:
- Validate file existence during initial load
- Log warning for missing files
- When user requests missing image via `!img`, reply with error (FR-084 from spec)

---

## Performance Metrics

### Polling Efficiency

**Expected API Usage**:
- Polling interval: 30 seconds
- Requests per day: 2,880 (well under 20,000 quota)
- Average response time: <500ms per polling request
- Cache hit rate: >95% (most polls find no changes)

**Success Criteria**:
- SC-006: Changes detected and applied within 60 seconds
- SC-007: Image retrieval completes within 10 seconds

### Bandwidth Considerations

**Typical File Sizes**:
- `system_prompt.md`: ~1-2 KB
- `image_map.json`: ~0.5-1 KB
- Image assets: 100 KB - 2 MB each

**Total Monthly Transfer** (worst case):
- Config files: ~2.5 KB × 60 syncs/hour × 720 hours = ~108 MB/month
- Image assets: 5 images × 1 MB × 10 downloads/day × 30 days = ~1.5 GB/month

---

## Contract Compliance

### Functional Requirements Coverage

- ✅ FR-017: Authenticate with Google Drive using service account
- ✅ FR-018: Maintain local cache of Google Drive files
- ✅ FR-019: Download `system_prompt.md`
- ✅ FR-020: Download `image_map.json`
- ✅ FR-021: Download image assets on demand
- ✅ FR-022: Automatically check Drive every 30-60 seconds
- ✅ FR-023: Detect changes by comparing timestamps/checksums
- ✅ FR-024: Apply changes automatically
- ✅ FR-025: Reload immediately on `!reload` command
- ✅ FR-026: Validate JSON before applying

### Testing Requirements

**Contract Tests** (to be implemented in `tests/contract/test_drive_sync.py`):
1. Test authentication with service account
2. Test file listing in folder
3. Test file download with MD5 verification
4. Test change detection with page tokens
5. Test cache invalidation on modified time change
6. Test JSON validation for `image_map.json`
7. Test error handling for API unavailable
8. Test manual `!reload` command bypass

**Example Test Case**:
```python
@pytest.mark.asyncio
async def test_drive_change_detection():
    """Verify change detection using page tokens"""
    service = init_drive_service()

    # Get initial page token
    token = get_start_page_token(service)

    # Simulate file change (mock or actual Drive edit)
    update_file_in_drive('system_prompt.md', 'Updated content')

    # Poll for changes
    changes = check_for_changes(service, token)

    # Assert change detected
    assert any(c['file']['name'] == 'system_prompt.md' for c in changes)
```

---

## Manual `!reload` Command

**Purpose**: Force immediate sync bypass cache (FR-005, FR-025)

**Implementation**:
```python
async def handle_reload_command(event):
    """Handle !reload command from authorized users"""
    # Optional: Check if user is admin
    if not is_admin_user(event.source.userId):
        await reply_message(event, "⚠️ 僅管理員可使用此指令 (Admin only)")
        return

    # Force re-download all config files
    logger.info("Manual reload triggered")
    await download_all_configs(force=True)

    # Validate and apply
    if validate_configs():
        await reply_message(event, "✅ 設定已重新載入 (Config reloaded)")
    else:
        await reply_message(event, "⚠️ 設定載入失敗 (Reload failed)")
```

---

## Next Steps

✅ **Drive Sync Contract Complete** → Proceed to Quickstart Guide
