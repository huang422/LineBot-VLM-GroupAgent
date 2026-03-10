# AI-LineBot: Production-Ready LINE Chatbot with Local VLM

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Ollama](https://img.shields.io/badge/Ollama-qwen3.5:35b-a3b-000000.svg?logo=ollama&logoColor=white)](https://ollama.ai/)
[![LINE](https://img.shields.io/badge/LINE-Messaging%20API-00C300.svg?logo=line&logoColor=white)](https://developers.line.biz/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg?logo=docker&logoColor=white)](https://docs.docker.com/compose/)
[![Google Drive](https://img.shields.io/badge/Google%20Drive-API-4285F4.svg?logo=googledrive&logoColor=white)](https://developers.google.com/drive)
[![APScheduler](https://img.shields.io/badge/APScheduler-3.10+-orange.svg)](https://apscheduler.readthedocs.io/)
[![CUDA](https://img.shields.io/badge/NVIDIA-CUDA-76B900.svg?logo=nvidia&logoColor=white)](https://developer.nvidia.com/cuda-zone)
[![Cloudflare](https://img.shields.io/badge/Cloudflare-Tunnel-F38020.svg?logo=cloudflare&logoColor=white)](https://www.cloudflare.com/)
[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://www.buymeacoffee.com/huang422)

A **production-ready LINE group chatbot** powered by local **Ollama reasoning model (qwen3.5:35b-a3b or qwen3.5:9b)**, enabling AI conversations, image analysis, web search, and webpage content extraction without cloud API dependencies. Features reasoning model support with streaming, automatic simplified→traditional Chinese conversion, time-aware responses, guaranteed reply mechanisms and GPU Async Management.

---

## Key Highlights

### Core Capabilities

- **AI Conversations** - Natural language Q&A powered by local Ollama reasoning model (qwen3.5:35b-a3b or qwen3.5:9b)
- **Vision Analysis** - Reply to images for instant multimodal analysis with optimized lightweight prompts
- **Auto Web Search** - LLM-driven search classification: automatically determines if a question needs real-time web data, date-aware queries
- **Manual Web Search** - `!web` command for explicit web search + AI response via Tavily AI (advanced depth, AI summary)
- **Webpage Extraction** - Automatic URL detection in messages, extracts full webpage content via Tavily Extract API with fallback search
- **Conversation Context** - Automatic tracking of last 5 messages per group for contextual responses
- **Smart Think Routing** - Auto-detects complex queries for `think=True` mode; simple queries use `think=False` (fast, fits 30s reply_token window); 300s timeout then guaranteed retry with `think=False`
- **Traditional Chinese Enforcement** - All output forced to 繁體中文 via OpenCC (simplified→traditional conversion)
- **Time Awareness** - Current Taiwan date/time injected into every prompt (no extra API calls)
- **Guaranteed Reply** - Every request gets a response: reply_token (FREE) → push_message (PAID, with elapsed time logged); timeout/error auto-notifies user
- **Smart Image Retrieval** - Keyword-based image search from Google Drive
- **Scheduled Messages** - Cron-based recurring notifications (APScheduler)
- **Live Configuration** - Google Drive sync for prompts and image mappings

### Architecture at a Glance

```
┌─────────────────────────────────────────────────────────────┐
│  LINE Messaging API (Webhook)                               │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│  FastAPI Server                                             │
│  ├─ Webhook Signature Validation (HMAC-SHA256)              │
│  ├─ Command Parser (!hej, !img, !web, !reload)              │
│  ├─ Context Manager (Last 5 messages/group)                 │
│  └─ Handler Router                                          │
└────────────────────┬────────────────────────────────────────┘
                     ↓
          ┌──────────┴──────────┐
          ↓                     ↓
┌──────────────────┐   ┌──────────────────────┐
│  LLM Pipeline    │   │  Image/Config Sync   │
│  ├─ Rate Limiter │   │  ├─ Google Drive API │
│  ├─ URL Extract  │   │  ├─ Local Cache      │
│  ├─ Auto Search  │   │  └─ Auto-reload      │
│  ├─ Queue System │   └──────────────────────┘
│  ├─ GPU Inference│
│  │  (streaming)  │
│  ├─ Think Filter │
│  ├─ S2T Convert  │
│  └─ Guaranteed   │
│     Reply        │
└──────────────────┘
```

### Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Web Framework** | FastAPI + Uvicorn | Async API server with webhook handling |
| **LLM Engine** | Ollama (qwen3.5:35b-a3b or qwen3.5:9b) | Local GPU-accelerated reasoning model (set via OLLAMA_MODEL) |
| **Web Search** | Tavily AI | Real-time web search + webpage content extraction |
| **Auto Search** | LLM Classification | Two-stage (keyword + LLM) search need detection |
| **URL Extraction** | Tavily Extract API | Automatic webpage content extraction from URLs |
| **Messaging** | LINE Messaging API | User interaction and webhook events |
| **Configuration** | Google Drive API | Collaborative prompt/image management |
| **Queue** | asyncio.Queue | Sequential GPU request processing with timeout |
| **Rate Limiting** | Sliding window | 30 req/min per user (configurable) |
| **Scheduling** | APScheduler | Recurring message delivery |
| **Image Processing** | Pillow + pillow-heif | Resize (max 800px), min 64px, HEIC/PNG→JPEG |
| **Chinese Conversion** | OpenCC | Forced simplified→traditional Chinese output |
| **Deployment** | Docker Compose | Multi-container orchestration |
| **Tunnel** | Cloudflare Tunnel | Public HTTPS webhook endpoint |
| **GPU** | NVIDIA CUDA | RTX 4080 (9GB VRAM limit via OLLAMA_MAX_VRAM) |

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

# Pull the model — choose one based on your hardware (set OLLAMA_MODEL in .env accordingly)
docker compose exec ollama ollama pull qwen3.5:35b-a3b  # high quality (~20GB, needs 32GB RAM)
# docker compose exec ollama ollama pull qwen3.5:9b     # fast (~5GB, fits in 12GB VRAM)

# Get the public webhook URL
docker compose logs cloudflared | grep trycloudflare.com
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
!hej 你好，今天星期幾？
!hej 請解釋什麼是機器學習
!web 2026 AI 最新趨勢
!img architecture
!reload
```

---

## Command Reference

### `!hej [question]` - AI-Powered Q&A

**Text Questions:**
```
!hej 台灣的首都是哪裡？
!hej 用 Python 寫一個斐波那契數列
!hej 現在幾點？  →  Bot knows current Taiwan time
```

**Auto Web Search** (Automatic):
```
!hej 今天台積電股價多少？  →  Auto-detects need for web search
!hej 台北現在幾度？         →  Triggers keyword-based fast search
!hej Python 怎麼寫迴圈？   →  No search needed, answers directly
```

**Vision Analysis** (Reply to images):
```
1. User sends an image in the chat
2. Reply to that image with: !hej 這張圖片裡有什麼？
3. Bot analyzes with lightweight VLM prompt (~2-3s)
```

**Context Mode** (Reply to text):
```
1. User says: "我在學 Python"
2. Reply: !hej 有什麼好的學習資源？
3. Bot includes quoted text as context
```

**Contextual Conversations** (Automatic):
```
User A: "今天天氣真好"
User B: "要不要去打球?"
User A: "!hej 幾點集合?"
→ Bot sees last 5 messages, understands the basketball context
```

**Smart Keyword** (Auto-delegates to !img):
```
!hej 騎哈雷  →  If keyword matches image_map, sends image directly
```

### `!img [keyword]` - Image Retrieval

```
!img architecture    # Diagram from Google Drive
!img 騎哈雷          # Image mapped to keyword
```

### `!web [query]` - Web Search + AI Response

Explicit web search using Tavily AI, results fed to LLM.

```
!web 台灣今天新聞
!web latest iPhone specs
!web Python 3.12 new features
```

**How it works:**
1. Current date (Taiwan timezone) prepended to query for time-sensitive accuracy
2. Tavily AI searches the web (advanced depth, 5 results, up to 2000 chars each)
3. AI-generated summary included alongside search results
4. Results are added to LLM prompt as context
5. LLM generates a response based on search results

**URL Extraction** (Automatic):
```
!hej 幫我摘要這個網頁 https://example.com  →  Extracts webpage content via Tavily Extract
!hej [reply to a URL message]              →  Detects URL in quoted message context
```
When URL extraction fails (e.g., Twitter/X blocks crawlers), automatically falls back to web search.

**Requirements:**
- Set `TAVILY_API_KEY` in `.env`
- Free tier: 1000 searches/month at [tavily.com](https://tavily.com/)

### `!reload` - Force Config Refresh

Manually triggers system prompt and image mapping reload from Google Drive.

---

## Configuration

### Environment Variables

**Required:**
```bash
LINE_CHANNEL_SECRET=your_secret
LINE_CHANNEL_ACCESS_TOKEN=your_token
```

**Optional - Ollama Model:**
```bash
OLLAMA_MODEL=qwen3.5:35b-a3b               # or qwen3.5:9b for speed — only this line needs changing
OLLAMA_BASE_URL=http://localhost:11434 # Ollama API endpoint
OLLAMA_NUM_PREDICT=6144                # Max tokens (thinking + response)
OLLAMA_TEMPERATURE=0.7                 # Creativity (0=deterministic)
OLLAMA_NUM_CTX=8192                    # Context window (8192 for image support)
```

**Optional - Performance:**
```bash
RATE_LIMIT_MAX_REQUESTS=30          # Per-user quota per window
RATE_LIMIT_WINDOW_SECONDS=60        # Window duration
QUEUE_MAX_SIZE=10                   # Max pending requests
QUEUE_TIMEOUT_SECONDS=480           # Full pipeline: classify(30) + search(20) + think(300) + sleep(2) + retry(90)
```

**Optional - Google Drive:**
```bash
GOOGLE_SERVICE_ACCOUNT_FILE=/app/credentials.json
DRIVE_FOLDER_ID=your_folder_id
DRIVE_SYNC_INTERVAL_SECONDS=120     # 30-120s range
```

**Optional - Server:**
```bash
PUBLIC_BASE_URL=https://your-tunnel.trycloudflare.com  # Required for !img
LOG_LEVEL=INFO                      # DEBUG/INFO/WARNING/ERROR
```

**Optional - Web Search (Tavily AI):**
```bash
TAVILY_API_KEY=tvly-xxxxxxxxxxxxx          # Get from tavily.com (free 1000/month)
AUTO_WEB_SEARCH_ENABLED=true               # LLM auto-detects search needs
WEB_SEARCH_MONTHLY_QUOTA=950               # Safety margin below API limit
```

**Optional - Scheduled Messages:**
```bash
SCHEDULED_MESSAGES_ENABLED=true
SCHEDULED_GROUP_ID=C1234567890abcdef...    # Get from webhook logs
```

---

## Architecture Details

### Project Structure

```
src/
├── models/                              # Pydantic data models
│   ├── llm_request.py                   # LLM request with multimodal support
│   ├── prompt_config.py                 # System prompt configuration
│   └── image_mapping.py                 # Image keyword mappings
├── services/                            # Business logic (singletons)
│   ├── ollama_service.py                # Streaming inference, think filter, S2T, time injection
│   ├── line_service.py                  # LINE API (reply/push/loading animation)
│   ├── queue_service.py                 # Async queue with guaranteed notifications
│   ├── drive_service.py                 # Google Drive sync
│   ├── image_service.py                 # Image resize (64-800px), base64 encoding
│   ├── rate_limit_service.py            # Per-user sliding window
│   ├── scheduler_service.py             # APScheduler cron jobs
│   ├── message_cache_service.py         # Quote/reply message cache
│   ├── conversation_context_service.py  # Last 5 messages per group
│   └── web_search_service.py            # Tavily AI search + URL content extraction
├── handlers/                            # Command routing
│   ├── command_handler.py               # !prefix parsing + quote detection
│   ├── hej_handler.py                   # !hej (auto search + image keyword)
│   ├── img_handler.py                   # !img image retrieval
│   ├── web_handler.py                   # !web explicit search
│   └── reload_handler.py               # !reload Drive sync
└── utils/
    ├── logger.py                        # Structured logging with context
    └── validators.py                    # Signature, sanitization, injection detection
```

### Key Design Decisions

**Think / No-Think Routing:**
```
Ollama qwen3.5:35b-a3b (or qwen3.5:9b) streaming API returns two separate fields:
  - "thinking" : internal reasoning (always hidden from user)
  - "response" : final answer (sent to user)

Controlled via Ollama API parameter "think": true/false (NOT text prefix).

  think=False  (no-think mode, ~80% of queries)
  ──────────────────────────────────────────────
  Trigger : no complex keywords detected
  Use case: casual chat, basic Q&A, image analysis
  Tokens  : num_predict=1024
  Speed   : 5–15s typical
  Reply   : likely within 30s → reply_token (FREE)

  think=True  (think mode, complex keywords detected)
  ──────────────────────────────────────────────
  Use case: in-depth analysis, architecture design, comparisons
  Tokens  : num_predict=6144 (shared by thinking + response)
            ⚠ thinking tokens are consumed FIRST; if thinking uses 3800
               tokens, only 296 remain for the actual response
  Speed   : 20–300s depending on complexity
  Reply   : likely >30s → reply_token expired → push_message (PAID)
  Fallback: if response empty (token exhaustion) OR timeout at 300s
            → sleep 2s → retry with think=False, num_predict=1024 (≤90s)

  Image analysis (separate path)
  ──────────────────────────────────────────────
  Always think=False (save tokens for vision encoder)
  num_predict=6144 (image tokens are large)
  Speed: 5–10s typical
```

**Reply Timing & Cost:**
```
T+0s    Webhook received → return 200 OK immediately (LINE requirement)
T+0s    Loading animation sent (FREE, shows "typing..." for 60s)
T+0s    LLM inference starts (includes auto-search classify + Tavily)

─────────────── 30s boundary: reply_token validity ───────────────

T<30s   LLM done → reply via reply_token         [FREE]
         log: [FREE] reply_token | elapsed=Xs

T>30s   LLM done → reply_token expired
         → push_message fallback               [PAID]
         log: [PAID] push_message | elapsed=Xs

─────────────── 300s: thinking timeout ───────────────

T=300s  think=True timed out → cancel inference
         → sleep 2s (let Ollama release connection)
         → retry: think=False, num_predict=1024 (timeout: 90s)
         → done at ~T+392s → push_message       [PAID]
         log: Retry with think=False succeeded

T<300s  think=True token exhaustion (6144 tokens fully consumed by thinking)
         → empty response → immediate retry: think=False, num_predict=1024
         log: Empty response (token_exhaustion), retrying

─────────────── 480s: queue hard timeout ───────────────

T=480s  Queue worker timeout → notify user      [FREE or PAID]
         "⚠️ 處理時間過長，請稍後再試。"

Exception → notify user                         [FREE or PAID]
         "❌ 處理請求時發生錯誤，請稍後再試。"

Every code path delivers a user-visible response.
```

**Image Analysis Optimization:**
```
Text requests:  full system prompt + context + history (~2000 tokens)
Image requests: minimal prompt, think=False via API (~500 tokens)

Images are resized to max 800px (saves ~1000 prompt tokens vs 1920px)
Minimum 64px enforced (avoids issues with very small images)
```

**Simplified → Traditional Chinese:**
```python
from opencc import OpenCC
_s2t = OpenCC('s2t')

# Applied at ALL return points in generate()
return _s2t.convert(response_text)  # 这张图片 → 這張圖片
```

**Time Awareness:**
```
Every request's system prompt starts with:
"現在時間：2026-02-12 星期四 12:20"

~10 tokens overhead, zero API calls.
Model can answer "今天星期幾？" without web search.
Search queries also prepend the current date for time-sensitive accuracy.
```

**GPU Async Management:**
```
Problem: GPU can only run one inference at a time.
         Multiple concurrent requests → VRAM contention → OOM crash.

Solution: Single-worker async queue with semaphore-based concurrency control.

┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│  Request A   │ → │              │ → │              │
│  Request B   │ → │  asyncio     │ → │  Semaphore   │ → GPU (1 at a time)
│  Request C   │ → │  Queue(10)   │ → │  (1)         │
└──────────────┘   └──────────────┘   └──────────────┘
    Webhook            Buffered         Sequential

- asyncio.Queue: max 10 pending requests, rejects when full
- asyncio.Semaphore(1): guarantees single concurrent GPU inference
- Non-blocking enqueue: webhook returns 200 immediately
- Background worker: continuously polls queue, processes sequentially
- Timeout: 480s per request (queue hard deadline), auto-notifies user on expiration
- Retry: 1 automatic retry on transient failure (if queue not full)
```

**VRAM Memory Control:**
```
GPU: NVIDIA RTX 4080 (16GB VRAM)

OLLAMA_MAX_VRAM=10737418240 (10GB limit)

Without limit:  Ollama uses ALL 12GB → OOM with 35b model
With 10GB limit: ~10GB model weights on GPU, remaining ~10GB offloaded to RAM
                 ~2GB VRAM reserved for OS/CUDA overhead

Model memory breakdown:
  qwen3.5:35b-a3b Q4_K_M (~20GB total):
    - GPU (VRAM):   ~10GB model layers (capped by OLLAMA_MAX_VRAM)
    - RAM offload:  ~10GB remaining layers (needs 32GB+ system RAM)
    - KV cache:     ~1-2GB  |  CUDA overhead: ~0.5GB
  qwen3.5:9b Q4_K_M (~5GB total):
    - GPU (VRAM):   ~5GB (fits fully in 12GB VRAM, no RAM offload needed)
    - KV cache:     ~1-2GB  |  CUDA overhead: ~0.5GB
  → Switch model: change OLLAMA_MODEL in .env, no other config change needed

Additional controls:
- num_ctx=8192:     Context window cap (limits KV cache memory)
- num_predict=6144: Max output tokens (limits generation memory)
- Image resize:     Max 800px (reduces vision encoder memory)
- Queue max=10:     Bounds total pending work
```

### Data Flow (!hej)

```
1.  LINE webhook → FastAPI
2.  Signature validation (HMAC-SHA256)
3.  Message cached + added to conversation context
4.  Command parsing (!hej + quoted message detection)
5.  Rate limit check
6.  Image keyword check (auto-delegates to !img if match)
7.  LLM request enqueued with context
8.  Queue worker processes (300s think timeout, 480s hard deadline)
9.  Loading animation sent (FREE)
10. URL detection in prompt + quoted message context
11. URL found → Tavily Extract (fallback: search by URL)
12. No URL → Auto search classification (keyword → LLM two-stage)
13. Date-prefixed web search via Tavily (if needed)
14. Ollama streaming inference (thinking + response fields)
15. OpenCC simplified → traditional Chinese conversion
16. Reply via reply_token (FREE) → push_message (fallback)
17. Bot response saved to conversation context
```

### Data Flow (Image Analysis)

```
1.  User sends image → cached with message_id
2.  User replies to image with "!hej 這是什麼？"
3.  Quoted message_id found in cache (type=image)
4.  Image downloaded from LINE Content API
5.  Resized to max 800px, min 64px, JPEG encoded
6.  Lightweight system prompt: "你是圖片分析助手..."
7.  think=False via Ollama API parameter (no reasoning overhead)
8.  Ollama inference (~5-10s for images)
9.  OpenCC conversion + reply
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
- **VRAM Limit** - `OLLAMA_MAX_VRAM=9GB` prevents GPU OOM

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
    "queue": {"current_size": 0, "max_size": 10, "total_processed": 127, "total_errors": 3},
    "rate_limit": {"active_trackers": 5, "max_requests": 30, "window_seconds": 60},
    "drive": {"is_configured": true, "prompt_version": 1, "image_mappings": 3},
    "scheduler": {"running": true, "job_count": 2},
    "conversation_context": {"groups_tracked": 5, "total_messages": 12, "max_messages_per_group": 5},
    "web_search_quota": {"month": "2026-02", "used": 15, "quota": 950, "remaining": 935}
  }
}
```

### Useful Commands

```bash
# View all service logs
docker compose logs -f

# View specific service
docker compose logs -f linebot
docker compose logs -f ollama

# Check GPU usage
nvidia-smi

# Check Ollama truncation warnings
docker compose logs ollama | grep truncat

# Monitor conversation context
docker compose logs -f linebot | grep "Conversation history"

# View scheduler jobs
curl -s http://localhost:8000/health | jq '.services.scheduler'

# Find group IDs
docker compose logs linebot | grep -o '"groupId": "[^"]*"' | sort -u
```

---

## Advanced Topics

### Custom Scheduled Messages

Edit `main.py`:
```python
scheduler_service.add_weekly_message(
    job_id="friday_reminder",
    day_of_week="fri",
    hour=18, minute=30,
    group_id=settings.scheduled_group_id,
    message="Weekend workout?",
)
```

### Google Drive Setup

Create this folder structure:
```
AI-LineBot Config/
├── system_prompt (Google Docs)      # LLM instructions
├── image_map (Google Sheets)        # keyword → filename mappings
└── images/
    ├── architecture.png
    └── workflow.jpg
```

**Important:** Add `必須使用繁體中文回覆，禁止輸出簡體中文字。` to your system prompt in Google Docs to enforce traditional Chinese at the LLM level as well.

---

## Additional Documentation

- [Full Setup Guide (Chinese)](START.md)
- [LINE Message Quota](https://manager.line.biz/)
- [Tavily Search Quota](https://app.tavily.com/home)

---

## License

GNU General Public License v3 (GPLv3) - see [LICENSE](LICENSE) file for details.

## Contact

For questions, issues, or collaboration inquiries:

- Developer: Tom Huang
- Email: huang1473690@gmail.com
