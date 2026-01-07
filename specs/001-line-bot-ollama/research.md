# Technology Research: LINE Bot with Local Ollama VLM Integration

**Feature**: [spec.md](./spec.md) | **Phase**: 0 (Research) | **Date**: 2026-01-07

## Purpose

This document captures research findings on key technologies and integration patterns required for implementing the LINE Bot with local Ollama VLM integration. Research focuses on practical implementation details, API contracts, and performance characteristics.

## 1. LINE Messaging API

### Webhook Integration

**Endpoint Requirements**:
- Must respond with HTTP 200 within 15 seconds
- Must validate `X-Line-Signature` header using HMAC-SHA256
- Signature validation formula: `HMAC-SHA256(channel_secret, request_body)`

**Example Webhook Event (Text Message)**:
```json
{
  "destination": "U1234567890abcdef1234567890abcdef",
  "events": [
    {
      "type": "message",
      "message": {
        "type": "text",
        "id": "325708",
        "text": "!hej What is the capital of France?"
      },
      "timestamp": 1462629479859,
      "source": {
        "type": "group",
        "groupId": "Ca56f94637c...",
        "userId": "U4af4980629..."
      },
      "replyToken": "b60d432864f44d079f6d8efe86cf404b"
    }
  ]
}
```

**Example Webhook Event (Reply with Quoted Message)**:
```json
{
  "events": [
    {
      "type": "message",
      "message": {
        "type": "text",
        "id": "325709",
        "text": "!hej What's in this image?",
        "quotedMessageId": "325700"
      },
      "source": {
        "type": "group",
        "groupId": "Ca56f94637c...",
        "userId": "U4af4980629..."
      },
      "replyToken": "..."
    }
  ]
}
```

**Retrieving Quoted Message Content**:
- Use `GET /v2/bot/message/{messageId}/content` to download images
- Signature validation required on all requests
- Content-Type header indicates image format (image/jpeg, image/png)

**Reply API**:
```python
# Reply using replyToken (valid for 60 seconds)
POST https://api.line.me/v2/bot/message/reply
{
  "replyToken": "b60d432864f44d079f6d8efe86cf404b",
  "messages": [
    {
      "type": "text",
      "text": "Paris is the capital of France."
    }
  ]
}

# Push message (no replyToken needed, for admin notifications)
POST https://api.line.me/v2/bot/message/push
{
  "to": "U4af4980629...",  # Admin user ID
  "messages": [
    {
      "type": "text",
      "text": "[ALERT] Ollama service is down"
    }
  ]
}
```

**Performance Characteristics**:
- Webhook timeout: 15 seconds (must return HTTP 200)
- Reply token validity: 60 seconds (after that, must use push API)
- Rate limits: Varies by plan (typically 500+ messages/day for free tier)

## 2. Ollama API Integration

### Local API Endpoint

**Default Configuration**:
- Base URL: `http://localhost:11434`
- No authentication required (local deployment)
- Supports streaming and blocking responses

### Text-Only Inference

```python
POST http://localhost:11434/api/generate
{
  "model": "gemma3:4b",
  "prompt": "What is the capital of France?",
  "system": "You are a helpful assistant in a LINE group chat.",
  "stream": false
}

# Response
{
  "model": "gemma3:4b",
  "created_at": "2026-01-07T12:34:56.789Z",
  "response": "Paris is the capital of France.",
  "done": true,
  "total_duration": 2500000000,  # nanoseconds (2.5s)
  "load_duration": 500000000,
  "prompt_eval_count": 20,
  "eval_count": 12
}
```

### Multimodal Inference (Vision)

```python
POST http://localhost:11434/api/generate
{
  "model": "gemma3:4b",
  "prompt": "What's in this image?",
  "system": "You are a helpful assistant analyzing images.",
  "images": ["iVBORw0KGgoAAAANSUhEUgAAAAUA..."],  # base64 encoded
  "stream": false
}
```

**Image Encoding Requirements**:
- Format: base64 string (raw bytes, no data URI prefix)
- Supported formats: JPEG, PNG, WebP
- Recommended max dimension: 1920px (resize before encoding)

**Memory Considerations**:
- gemma3:4b model: ~4-5GB VRAM when loaded
- RTX 4080 12GB: Sufficient headroom for single inference
- Sequential processing (concurrency=1) prevents OOM errors

**Performance Expectations**:
- Text-only: 1-3 seconds for 20-50 token responses
- Multimodal: 5-15 seconds depending on image size
- Model loading: 0.5-1 second (cached after first request)

## 3. Google Drive API

### Authentication

**Service Account Setup**:
```python
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
credentials = service_account.Credentials.from_service_account_file(
    'service_account_key.json', scopes=SCOPES
)
service = build('drive', 'v3', credentials=credentials)
```

**Required Permissions**:
- Service account email must have "Viewer" access to shared folder
- Folder must be explicitly shared with service account email
- No domain-wide delegation required for this use case

### Polling for Changes

**Using Changes API with Page Tokens**:
```python
# Initial page token (run once at startup)
response = service.changes().getStartPageToken().execute()
page_token = response.get('startPageToken')

# Poll for changes every 30-60 seconds
while True:
    response = service.changes().list(
        pageToken=page_token,
        spaces='drive',
        fields='nextPageToken,newStartPageToken,changes(fileId,file(name,modifiedTime,md5Checksum))'
    ).execute()

    for change in response.get('changes', []):
        file_info = change.get('file')
        if file_info and file_info['name'] in ['system_prompt.md', 'image_map.json']:
            # Download and cache updated file
            download_and_cache(file_info)

    page_token = response.get('nextPageToken') or response.get('newStartPageToken')
    await asyncio.sleep(30)  # Poll every 30 seconds
```

### File Download

```python
# Download file content
request = service.files().get_media(fileId=file_id)
fh = io.BytesIO()
downloader = MediaIoBaseDownload(fh, request)
done = False
while not done:
    status, done = downloader.next_chunk()

content = fh.getvalue()
```

**Caching Strategy**:
- Store file locally with `md5Checksum` metadata
- Compare checksum on each poll to detect changes
- Use LRU eviction if cache exceeds size limit (e.g., 100MB)

**API Quota Considerations**:
- Free tier: 20,000 requests/day (polling every 30s = 2,880 requests/day)
- Caching reduces quota consumption significantly
- Use `fields` parameter to minimize response size

## 4. FastAPI Startup Workers (Constantly-Running Daemon)

### Pattern for Persistent Worker

```python
from fastapi import FastAPI, Request
import asyncio

app = FastAPI()
task_queue = asyncio.Queue(maxsize=10)

@app.on_event("startup")
async def startup_event():
    """Launch background workers when FastAPI starts"""
    # Start LLM worker (runs forever)
    asyncio.create_task(llm_worker())
    # Start Drive sync worker (runs forever)
    asyncio.create_task(drive_sync_worker())
    logger.info("Background workers started")

async def llm_worker():
    """Constantly-running worker processing LLM queue"""
    while True:
        try:
            request = await task_queue.get()
            async with semaphore:  # Only 1 at a time
                response = await ollama_service.generate(request)
                await line_service.reply(request, response)
            task_queue.task_done()
        except Exception as e:
            logger.error(f"Worker error: {e}")

async def drive_sync_worker():
    """Constantly-running worker polling Google Drive"""
    while True:
        try:
            await drive_service.check_for_changes()
            await asyncio.sleep(30)  # Poll every 30s
        except Exception as e:
            logger.error(f"Drive sync error: {e}")
            await asyncio.sleep(60)  # Retry after 1min on error

@app.post("/webhook")
async def webhook(request: Request):
    """Webhook endpoint - just enqueues and returns immediately"""
    signature = request.headers.get('X-Line-Signature')
    body = await request.body()

    if not validate_signature(body, signature):
        return {"status": "error"}, 403

    events = parse_line_events(body)
    for event in events:
        if should_process(event):
            try:
                task_queue.put_nowait(event)  # Non-blocking enqueue
            except asyncio.QueueFull:
                await send_busy_message(event)

    return {"status": "ok"}  # Return within <1s
```

**Key Benefits**:
- ✅ Workers start once at app startup, run forever
- ✅ No per-request task creation overhead
- ✅ Webhook responds in <1s (just enqueues)
- ✅ Worker never stops, always waiting with `await queue.get()`
- ✅ Matches daemon/systemd deployment model

**Trade-off Analysis**:
- ✅ Prevents webhook timeout (LINE requires <15s response)
- ✅ Allows long-running LLM inference (up to 30s+)
- ⚠️ Reply token expires after 60s (fallback to push API if processing slow)

## 5. Async Queue with Semaphore

### Implementation Pattern

```python
import asyncio

# Global queue and semaphore
queue = asyncio.Queue(maxsize=10)
semaphore = asyncio.Semaphore(1)  # Only 1 concurrent LLM request

async def worker():
    """Background worker processing queue sequentially"""
    while True:
        request = await queue.get()
        try:
            async with semaphore:
                # Only 1 request at a time reaches here
                response = await call_ollama_api(request)
                await send_line_reply(request, response)
        except Exception as e:
            logger.error(f"Worker error: {e}")
            await send_error_reply(request)
        finally:
            queue.task_done()

# Start worker at application startup
@app.on_event("startup")
async def startup():
    asyncio.create_task(worker())
```

### Queue Full Handling

```python
async def enqueue_request(request):
    try:
        queue.put_nowait(request)
        return True
    except asyncio.QueueFull:
        # Send immediate rejection
        await send_line_reply(
            request,
            "⏳ 系統忙碌中，請稍後再試 (Queue full, please retry later)"
        )
        return False
```

**Performance Characteristics**:
- Sequential processing ensures GPU stability
- Max queue depth (10) = ~5 minutes max wait (10 * 30s)
- Queue metrics should be logged for monitoring

## 6. In-Memory Image Processing

### LINE Image → Pillow → Base64 Pipeline

```python
from PIL import Image
import io
import base64
import aiohttp

async def download_and_process_image(message_id: str) -> str:
    """Download LINE image, resize in-memory, return base64"""

    # Download image to BytesIO (no disk write)
    async with aiohttp.ClientSession() as session:
        headers = {'Authorization': f'Bearer {LINE_CHANNEL_ACCESS_TOKEN}'}
        async with session.get(
            f'https://api-data.line.me/v2/bot/message/{message_id}/content',
            headers=headers
        ) as resp:
            image_bytes = await resp.read()

    # Load into Pillow from memory
    image = Image.open(io.BytesIO(image_bytes))

    # Resize if needed (preserve aspect ratio)
    if max(image.size) > 1920:
        ratio = 1920 / max(image.size)
        new_size = tuple(int(dim * ratio) for dim in image.size)
        image = image.resize(new_size, Image.Resampling.LANCZOS)

    # Encode to base64 in-memory
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    buffer.seek(0)
    base64_image = base64.b64encode(buffer.read()).decode('utf-8')

    # All objects garbage collected (no disk persistence)
    return base64_image
```

**Memory Efficiency**:
- BytesIO objects are temporary (garbage collected after function exit)
- Pillow operations in-memory only
- Typical memory usage: 10-20MB per image (1920px PNG)

**Privacy Compliance**:
- Zero disk writes for user images
- Only Google Drive static assets cached locally
- FR-009, FR-015, SC-011 compliance

## 7. Rate Limiting

### Per-User Sliding Window

```python
from collections import defaultdict
from datetime import datetime, timedelta

class RateLimiter:
    def __init__(self, max_requests: int = 30, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window = timedelta(seconds=window_seconds)
        self.requests = defaultdict(list)  # user_id -> [timestamps]

    def is_allowed(self, user_id: str) -> tuple[bool, int]:
        """Returns (allowed, seconds_until_reset)"""
        now = datetime.now()
        cutoff = now - self.window

        # Remove old requests
        self.requests[user_id] = [
            ts for ts in self.requests[user_id] if ts > cutoff
        ]

        # Check limit
        if len(self.requests[user_id]) >= self.max_requests:
            oldest = min(self.requests[user_id])
            reset_time = int((oldest + self.window - now).total_seconds())
            return False, reset_time

        # Record request
        self.requests[user_id].append(now)
        return True, 0
```

**Persistent Storage (Optional Enhancement)**:
- Use Redis for multi-instance deployments
- For single-instance: in-memory dict is sufficient
- Fallback to IP-based limiting if user_id unavailable

## 8. Cloudflare Tunnel

### Setup and Configuration

**Installation**:
```bash
# Install cloudflared
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared-linux-amd64.deb

# Authenticate
cloudflared tunnel login

# Create tunnel
cloudflared tunnel create linebot-tunnel

# Configure tunnel
cat > ~/.cloudflared/config.yml <<EOF
tunnel: linebot-tunnel
credentials-file: /home/user/.cloudflared/<tunnel-id>.json

ingress:
  - hostname: linebot.example.com
    service: http://localhost:8000
  - service: http_status:404
EOF

# Run tunnel
cloudflared tunnel run linebot-tunnel
```

**Integration with FastAPI**:
- FastAPI runs on `localhost:8000`
- Cloudflare Tunnel exposes public HTTPS URL
- LINE webhook configured to `https://linebot.example.com/webhook`
- No firewall configuration needed

**Security Considerations**:
- Tunnel provides automatic HTTPS
- Origin certificate validates tunnel identity
- No exposed ports on local machine
- LINE signature validation remains critical (don't trust tunnel alone)

## Research Validation

### Coverage Checklist

- [x] LINE Messaging API webhook integration (FR-038, FR-039, FR-040)
- [x] LINE image download via Content API (FR-042)
- [x] Ollama text and multimodal API contracts (FR-006, FR-007, FR-010)
- [x] Google Drive authentication and polling (FR-017, FR-022, FR-023)
- [x] FastAPI BackgroundTasks pattern (FR-051)
- [x] Async queue with semaphore (FR-031, FR-032)
- [x] In-memory image processing (FR-008, FR-009)
- [x] Rate limiting strategy (FR-049)
- [x] Cloudflare Tunnel deployment (Constraint: public webhook access)

### Key Findings

1. **LINE webhook timeout is strict (15s)** → BackgroundTasks pattern mandatory
2. **Ollama gemma3:4b fits in 12GB VRAM** → Sequential processing prevents OOM
3. **Google Drive Changes API efficient** → Polling every 30s well within quota
4. **In-memory image pipeline feasible** → BytesIO + Pillow + base64 (no disk I/O)
5. **Cloudflare Tunnel simplifies deployment** → No manual firewall/reverse proxy setup

## Next Steps

✅ **Phase 0 Complete** → Proceed to Phase 1 (Data Models, Contracts, Quickstart)
