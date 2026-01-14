# AI-LineBot: Production-Ready LINE Chatbot with Local VLM

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Ollama](https://img.shields.io/badge/Ollama-gemma3:12b-000000.svg?logo=ollama&logoColor=white)](https://ollama.ai/)
[![LINE](https://img.shields.io/badge/LINE-Messaging%20API-00C300.svg?logo=line&logoColor=white)](https://developers.line.biz/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg?logo=docker&logoColor=white)](https://docs.docker.com/compose/)
[![Google Drive](https://img.shields.io/badge/Google%20Drive-API-4285F4.svg?logo=googledrive&logoColor=white)](https://developers.google.com/drive)
[![APScheduler](https://img.shields.io/badge/APScheduler-3.10+-orange.svg)](https://apscheduler.readthedocs.io/)
[![CUDA](https://img.shields.io/badge/NVIDIA-CUDA-76B900.svg?logo=nvidia&logoColor=white)](https://developer.nvidia.com/cuda-zone)
[![Cloudflare](https://img.shields.io/badge/Cloudflare-Tunnel-F38020.svg?logo=cloudflare&logoColor=white)](https://www.cloudflare.com/)
[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://www.buymeacoffee.com/huang422)

A **production-ready LINE group chatbot** powered by local **Ollama Vision-Language Models (VLM)**, enabling AI conversations and image analysis without cloud API dependencies. Built with **FastAPI** and enterprise-level architecture: async queue management, rate limiting, Google Drive integration, GPU-optimized inference, and scheduled messaging.

---

## Key Highlights

### Core Capabilities

- **AI Conversations** - Natural language Q&A powered by local Ollama LLM (gemma3:12b)
- **Conversation Context** - Automatic tracking of last 5 messages per group for contextual responses
- **Vision Analysis** - Reply to images with questions for instant multimodal analysis
- **Smart Image Retrieval** - Keyword-based image search from Google Drive
- **Scheduled Messages** - Cron-based recurring notifications (APScheduler)
- **Live Configuration** - Google Drive sync for prompts and image mappings
- **Production Architecture** - Async queue, rate limiting, health checks, structured logging

### Architecture at a Glance

```
┌─────────────────────────────────────────────────────────────┐
│  LINE Messaging API (Webhook)                               │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│  FastAPI Server                                             │
│  ├─ Webhook Signature Validation (HMAC-SHA256)              │
│  ├─ Command Parser (!hej, !img, !reload)                    │
│  ├─ Context Manager (Last 5 messages/group)                 │
│  └─ Handler Router                                          │
└────────────────────┬────────────────────────────────────────┘
                     ↓
          ┌──────────┴──────────┐
          ↓                     ↓
┌──────────────────┐   ┌──────────────────────┐
│  LLM Pipeline    │   │  Image/Config Sync   │
│  ├─ Rate Limiter │   │  ├─ Google Drive API │
│  ├─ Queue System │   │  ├─ Local Cache      │
│  ├─ GPU Inference│   │  └─ Auto-reload      │
│  └─ Response     │   └──────────────────────┘
└──────────────────┘
```

### Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Web Framework** | FastAPI + Uvicorn | Async API server with webhook handling |
| **LLM Engine** | Ollama (gemma3:12b) | Local GPU-accelerated inference (4B params) |
| **Messaging** | LINE Messaging API | User interaction and webhook events |
| **Configuration** | Google Drive API | Collaborative prompt/image management |
| **Queue** | asyncio.Queue | Sequential GPU request processing |
| **Rate Limiting** | Sliding window | 30 req/min per user (configurable) |
| **Scheduling** | APScheduler | Recurring message delivery |
| **Image Processing** | Pillow + pillow-heif | HEIC/PNG to JPEG conversion |
| **Deployment** | Docker Compose | Multi-container orchestration |
| **Tunnel** | Cloudflare Tunnel | Public HTTPS webhook endpoint |
| **GPU** | NVIDIA CUDA | RTX 4080 (or compatible) |

---

## Quick Start (5 Minutes)

### Prerequisites

- **Docker** & **Docker Compose** (v2.0+)
- **NVIDIA GPU** with CUDA support
- **LINE Developers Account** ([Register here](https://developers.line.biz/))
- **Google Cloud Project** (Optional, for Drive sync)

### 1. Clone & Configure

```bash
git clone https://github.com/yourusername/AI-linebot.git
cd AI-linebot
cp .env.example .env
```

Edit `.env` with your LINE credentials:
```bash
LINE_CHANNEL_SECRET=your_secret_here
LINE_CHANNEL_ACCESS_TOKEN=your_token_here
```

### 2. Launch

```bash
# Start all services (linebot + ollama + cloudflared)
docker compose up -d

# Pull the LLM model (first time only, ~2.5GB)
docker compose exec ollama ollama pull gemma3:12b

# Get the public webhook URL
docker compose logs cloudflared | grep trycloudflare.com
# Example output: https://random-subdomain.trycloudflare.com
```

### 3. Configure LINE Webhook

1. Go to [LINE Developers Console](https://developers.line.biz/)
2. Navigate to your channel → **Messaging API** tab
3. Set **Webhook URL**: `https://your-tunnel-url.trycloudflare.com/webhook`
4. Enable **Use webhook** and disable **Auto-reply messages**
5. Click **Verify** to test

### 4. Test

Add the bot to a LINE group:
```
!hej What is machine learning?
!img architecture
!reload
```

---

## Command Reference

### `!hej [question]` - AI-Powered Q&A

**Text Questions:**
```
!hej What is the capital of France?
!hej Explain quantum computing simply
```

**Contextual Conversations** (Automatic):
```
User A: "今天天氣真好"
User B: "要不要去打球?"
Bot:    "聽起來不錯!"
User A: "!hej 幾點集合?"
→ Bot automatically sees last 5 messages and understands the context
```

**Vision Analysis** (Reply to images):
```
1. User sends an image
2. Reply with: !hej Describe this image
3. Bot analyzes and responds
```

**Context Mode** (Reply to text):
```
1. User says: "I'm learning Python"
2. Reply: !hej What are good resources?
3. Bot includes quoted text as context
```

**Smart Keyword** (Auto-delegates to !img):
```
!hej architecture  →  Sends architecture diagram
```

### `!img [keyword]` - Image Retrieval

```
!img architecture    # Diagram from Google Drive
!img workflow       # Workflow chart
```

Error handling:
```
Keyword "xyz" not found.
Available: architecture, workflow, diagram...
```

### `!reload` - Force Config Refresh

Manually triggers:
- System prompt reload from Drive
- Image mapping reload
- Cache refresh

---

## Configuration

### Environment Variables

**Required:**
```bash
LINE_CHANNEL_SECRET=your_secret
LINE_CHANNEL_ACCESS_TOKEN=your_token
```

**Optional - Performance:**
```bash
RATE_LIMIT_MAX_REQUESTS=30          # Per-user quota
RATE_LIMIT_WINDOW_SECONDS=60        # Window duration
QUEUE_MAX_SIZE=10                   # Max pending requests
QUEUE_TIMEOUT_SECONDS=120           # Request timeout
```

**Optional - Google Drive:**
```bash
GOOGLE_SERVICE_ACCOUNT_FILE=/app/credentials.json
DRIVE_FOLDER_ID=your_folder_id
DRIVE_SYNC_INTERVAL_SECONDS=45      # 30-120s range
```

**Optional - Server:**
```bash
PUBLIC_BASE_URL=https://your-tunnel.trycloudflare.com  # Required for !img
LOG_LEVEL=INFO                      # DEBUG/INFO/WARNING/ERROR
```

**Optional - Scheduled Messages:**
```bash
SCHEDULED_MESSAGES_ENABLED=true
SCHEDULED_GROUP_ID=C1234567890abcdef...  # Get from logs
```

### Google Drive Setup

Create this folder structure:
```
AI-LineBot Config/
├── system_prompt.md (google doc)   # LLM instructions
├── image_map.json (google sheet)   # Keyword mappings
└── images/
    ├── architecture.png
    └── workflow.jpg
```

**system_prompt.md:**
```markdown
You are a helpful AI assistant in a LINE group chat.
Respond concisely in the user's language.
Be friendly but professional.
```

**image_map.json:**
```json
{
  "mappings": [
    {
      "keyword": "architecture",
      "filename": "architecture.png",
      "file_id": "1ABC...XYZ"
    }
  ],
  "version": "1.0"
}
```

---

## Architecture Details

### Project Structure

```
src/
├── models/              # Pydantic data models
│   ├── llm_request.py
│   ├── prompt_config.py
│   └── image_mapping.py
├── services/            # Business logic (singleton)
│   ├── line_service.py
│   ├── ollama_service.py
│   ├── drive_service.py
│   ├── queue_service.py
│   ├── scheduler_service.py
│   ├── message_cache_service.py
│   └── conversation_context_service.py  # NEW: Context tracking
├── handlers/            # Command routing
│   ├── hej_handler.py
│   ├── img_handler.py
│   └── reload_handler.py
└── utils/               # Helpers
    ├── logger.py
    └── validators.py
```

### Design Patterns

**Singleton Services:**
```python
from src.services.line_service import get_line_service
line_service = get_line_service()  # Global instance
```

**Async Queue:**
```python
# Handler enqueues
request = LLMRequest(...)
queue_service.try_enqueue_nowait(request)

# Worker processes sequentially
await process_llm_request(request)
```

**Rate Limiting:**
```python
allowed, reset, remaining = await rate_limit_service.check_and_record(user_id)
if not allowed:
    return f"Rate limit exceeded. Retry in {reset}s"
```

### Data Flow (!hej)

```
1. LINE webhook → FastAPI
2. Signature validation (HMAC-SHA256)
3. Message saved to conversation context (last 5/group)
4. Command parsing
5. Rate limit check
6. Context retrieval (recent conversation history)
7. Queue enqueue with context
8. Background worker
9. Ollama GPU inference (with context in prompt)
10. LINE response
11. Bot response saved to context
```

---

## Security

### Implemented Protections

- **Webhook Signature** - HMAC-SHA256 constant-time comparison
- **Prompt Injection Detection** - 12+ regex patterns
- **Input Sanitization** - 4000 char limit, whitespace normalization
- **Rate Limiting** - Per-user sliding window quotas
- **OAuth2 Service Account** - Google Drive (no embedded credentials)
- **Non-Root Container** - Docker runs as `appuser`
- **Secret Management** - `.gitignore` excludes credentials
- **Timeout Enforcement** - All external APIs have limits

---

## Conversation Context System

### How It Works

The bot automatically tracks the **last 5 messages** in each group to provide contextual responses. This happens transparently without any user action needed.

#### Technical Implementation

**1. Message Storage**
```python
# Every incoming message is automatically saved
add_context_message(group_id, user_id, message_text, message_type)

# Uses deque with maxlen=5 (memory-efficient)
# Older messages are automatically discarded
```

**2. Context Retrieval**
When a user sends `!hej`, the bot:
```python
# Gets last 5 messages for this group
conversation_history = get_context_as_text(group_id, max_messages=5)

# Example output:
# User_U111: 今天天氣真好
# User_U222: 要不要去打球?
# Bot: 聽起來不錯!
# User_U222: 下午3點?
# User_U111: 好的
```

**3. Prompt Construction**
The context is integrated into the LLM prompt:
```
Recent conversation:
---
User_U111: 今天天氣真好
User_U222: 要不要去打球?
Bot: 聽起來不錯!
---

User's question: 幾點集合?
```

This allows the LLM to understand that "幾點集合?" is about the earlier basketball discussion.

### Features

- **Automatic**: No special commands needed
- **Group-Isolated**: Each group has independent context
- **Memory-Efficient**: Max 5 messages × ~200 bytes = ~1KB per group
- **TTL**: Messages expire after 1 hour
- **Zero Cost**: No LINE API calls (pure memory operations)

### Monitoring Context

**View in Docker logs:**
```bash
# See context updates in real-time
docker compose logs -f linebot | grep "Current context"

# View context used for LLM requests
docker compose logs -f linebot | grep "Conversation history"
```

**Example log output:**
```
[INFO] conversation_context: 📝 Current context for group C1234567... (3 messages):
  1. User_U111: 今天天氣真好
  2. User_U222: 要不要去打球?
  3. Bot: 聽起來不錯!
```

**Health endpoint stats:**
```bash
curl http://localhost:8000/health | jq '.services.conversation_context'
```

Output:
```json
{
  "groups_tracked": 5,
  "total_messages": 23,
  "max_messages_per_group": 5,
  "ttl_seconds": 3600
}
```

### Supported Message Types

| Type | Storage | Display in Context |
|------|---------|-------------------|
| Text | Full content | `User_xxx: 訊息內容` |
| Image | Metadata only | `User_xxx: [發送了圖片]` |
| Sticker | Metadata only | `User_xxx: [發送了貼圖]` |
| Bot Reply | Full content | `Bot: 回覆內容` |

---

## Monitoring

### Health Endpoint

```bash
curl http://localhost:8000/health | jq
```

**Response:**
```json
{
  "status": "healthy",
  "services": {
    "ollama": "up",
    "queue": {"size": 2, "processed": 127, "errors": 3},
    "drive": {"configured": true, "cache_hits": 112},
    "scheduler": {
      "running": true,
      "jobs": [{
        "id": "monday_reminder",
        "next_run": "2026-01-19T21:00:00+08:00"
      }]
    },
    "conversation_context": {
      "groups_tracked": 5,
      "total_messages": 23,
      "max_messages_per_group": 5,
      "ttl_seconds": 3600
    }
  }
}
```

### Logging

```bash
# Development (human-readable)
docker compose logs -f linebot

# Production (JSON)
LOG_LEVEL=INFO
```

---

## Use Cases

### 1. Technical Support Bot
- System prompt: IT helpdesk assistant
- Image mapping: VPN setup guides
- Scheduled: Monday password reminders

### 2. Educational Study Group
- System prompt: Teaching assistant
- Image mapping: Formula sheets
- Vision: Homework problem solving

### 3. Fitness Community
- System prompt: Fitness coach
- Image mapping: Workout plans
- Scheduled: Weekly workout reminders

### 4. Customer Service
- System prompt: Support representative
- Image mapping: Return policies
- Vision: Product defect triage

---

## Advanced Topics

### Custom Scheduled Messages

Edit `main.py`:
```python
scheduler_service.add_weekly_message(
    job_id="friday_reminder",
    day_of_week="fri",      # mon/tue/wed/thu/fri/sat/sun
    hour=18,                # 24-hour format
    minute=30,
    group_id=settings.scheduled_group_id,
    message="Weekend workout?",
)
```

### Multi-Model Support

```bash
# Pull different models
docker compose exec ollama ollama pull llama3.2-vision:11b

# Update .env
OLLAMA_MODEL=llama3.2-vision:11b

# Restart
docker compose restart linebot
```

### Finding Group IDs

```bash
# Monitor in real-time
docker compose logs -f linebot | grep "groupId"

# Send message in group, then:
docker compose logs linebot | grep "Full event structure" | tail -1
```

---

## Troubleshooting

### Bot Not Responding

```bash
# Check webhook
curl -X POST https://your-tunnel.trycloudflare.com/webhook \
  -H "Content-Type: application/json" \
  -d '{"events":[]}'

# Check logs
docker compose logs --tail=100 linebot
```

### Ollama Issues

```bash
# Verify model
docker compose exec ollama ollama list

# Re-pull
docker compose exec ollama ollama pull gemma3:12b

# Check GPU
docker compose exec ollama nvidia-smi
```

### Drive Sync Failing

```bash
# Verify credentials
docker compose exec linebot ls -la /app/credentials.json

# Enable debug
LOG_LEVEL=DEBUG
docker compose restart linebot
```

---

### Architecture Decisions

**Q: Why local Ollama vs cloud APIs?**
- Cost: No per-request charges
- Privacy: Data never leaves server
- Latency: Sub-second with GPU
- Offline: Works without internet

**Q: Why sequential GPU processing?**
- Prevents OOM on single-GPU systems
- Predictable performance
- Simple scaling (add workers for multi-GPU)

**Q: Why Google Drive config?**
- Non-technical users can edit prompts
- Version control via Drive history
- Zero-downtime reload
- Automatic cloud backup

### Technical Challenges Solved

**1. Reply Token Expiration**
- Problem: Tokens expire in ~60s
- Solution: Try reply first, fallback to push
- Code: `main.py:118-151`

**2. GPU Memory Management**
- Problem: Concurrent requests cause OOM crashes
- Solution: Semaphore-based sequential processing
- Code: `queue_service.py:55-60`

**3. Image Format Compatibility**
- Problem: LINE doesn't support HEIC
- Solution: Auto-convert to JPEG
- Code: `image_service.py:122-134`

**4. Webhook Security**
- Problem: Prevent spoofed requests
- Solution: HMAC-SHA256 validation
- Code: `validators.py:15-45`

### Code Quality

- **Async/Await:** Fully async (no blocking)
- **Error Handling:** Custom exceptions
- **Testing:** Health checks, structured logs
- **Documentation:** README, specs, inline comments

---

## Additional Documentation

- [Full Setup Guide (Chinese)](START.md)
- [Feature Specification](specs/001-line-bot-ollama/spec.md)
- [Implementation Plan](specs/001-line-bot-ollama/plan.md)

### External Resources

- [LINE Messaging API Docs](https://developers.line.biz/en/docs/messaging-api/)
- [Ollama Python Client](https://github.com/ollama/ollama-python)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Google Drive API v3](https://developers.google.com/drive/api/v3/about-sdk)

---

## License

This project is available for educational and portfolio demonstration purposes.

## Contact
For questions, issues, or collaboration inquiries:

- Developer: Tom Huang
- Email: huang1473690@gmail.com
