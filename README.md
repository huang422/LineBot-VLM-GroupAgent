# LINE Bot with Local Ollama VLM Integration

A headless LINE group chatbot backend with keyword-triggered responses (`!hej`, `!img`, `!reload`) that integrates with a locally-deployed Ollama gemma3 4B VLM on RTX 4080 GPU.

**具備 Ollama 本機 VLM 整合的 LINE 群組聊天機器人**，支援關鍵字觸發回應（`!hej`、`!img`、`!reload`），可在 RTX 4080 GPU 上執行本機部署的 Ollama gemma3 4B 視覺語言模型。

---

## 📖 Documentation | 文件

- **🚀 5 分鐘快速啟動**：[QUICKSTART.md](QUICKSTART.md)（中文）
- **📚 完整設定教學**：[docs/setup-guide-zh-TW.md](docs/setup-guide-zh-TW.md)（中文）
- **🔧 English Documentation**: See below

---

## Features

- **!hej [question]** - Ask the AI assistant questions, supports multimodal (image analysis) via reply
- **!img [keyword]** - Retrieve predefined images by keyword
- **!reload** - Force refresh configuration from Google Drive

## Architecture

- **Framework**: FastAPI with async request handling
- **LLM**: Ollama with gemma3:4b model (or any Ollama-compatible VLM)
- **Storage**: Google Drive for collaborative prompt/image management
- **Queue**: Async queue with max 10 pending requests, sequential processing (concurrency=1)
- **Rate Limiting**: 30 requests/minute per user
- **Deployment**: Cloudflare Tunnel for public webhook access

## Quick Start

### Prerequisites

- Python 3.11+
- Ollama with gemma3:4b model (`ollama pull gemma3:4b`)
- LINE Messaging API credentials
- (Optional) Google Cloud service account for Drive integration

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd AI-linebot

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment template and configure
cp .env.example .env
# Edit .env with your credentials
```

### Configuration

Edit `.env` with your credentials:

```bash
# Required
LINE_CHANNEL_SECRET=your_channel_secret
LINE_CHANNEL_ACCESS_TOKEN=your_access_token

# Optional (for Google Drive integration)
GOOGLE_SERVICE_ACCOUNT_FILE=/path/to/service_account.json
DRIVE_FOLDER_ID=your_drive_folder_id
```

### Running

#### 方法一：Docker Compose（推薦！✨）

**一鍵啟動所有服務（Bot + Ollama + Cloudflare Tunnel）：**

```bash
# 快速啟動（推薦使用此腳本）
./start.sh

# 或手動啟動
docker-compose up -d

# 查看 Cloudflare Tunnel URL（用於設定 LINE Webhook）
./get-url.sh

# 或手動查看
docker logs cloudflared 2>&1 | grep "https://"

# 下載模型（首次使用）
docker-compose exec ollama ollama pull gemma3:4b

# 查看日誌
docker-compose logs -f linebot

# 停止所有服務
docker-compose down
```

**重要：將顯示的 Cloudflare URL 設定到 LINE Developers Console 的 Webhook URL**

範例：`https://xxxxx.trycloudflare.com/webhook`

詳細設定請參考 [`docs/setup-guide-zh-TW.md`](docs/setup-guide-zh-TW.md)

#### 方法二：手動執行（開發模式）

```bash
# 終端機 1 - Ollama
ollama serve

# 終端機 2 - LINE Bot
python main.py

# 終端機 3 - Cloudflare Tunnel
cloudflared tunnel --url http://localhost:8000
```

### Webhook Setup

1. Expose your server via Cloudflare Tunnel or ngrok
2. Set webhook URL in LINE Developers Console: `https://your-domain/webhook`
3. Enable webhook and disable auto-reply in LINE Official Account settings

## Project Structure

```
src/
├── main.py              # FastAPI app, webhook endpoint, background workers
├── config.py            # Environment configuration
├── models/              # Data models
│   ├── llm_request.py   # LLM request queue item
│   ├── prompt_config.py # System prompt configuration
│   ├── image_mapping.py # Keyword-to-image mappings
│   ├── cached_asset.py  # Drive file cache metadata
│   └── rate_limit.py    # Per-user rate limiting
├── services/            # Business logic
│   ├── line_service.py  # LINE API integration
│   ├── ollama_service.py # Ollama LLM integration
│   ├── drive_service.py # Google Drive sync
│   ├── queue_service.py # Async request queue
│   ├── image_service.py # In-memory image processing
│   └── rate_limit_service.py # Rate limiting
├── handlers/            # Command handlers
│   ├── command_handler.py # Command parsing and routing
│   ├── hej_handler.py   # !hej command
│   ├── img_handler.py   # !img command
│   └── reload_handler.py # !reload command
└── utils/               # Utilities
    ├── logger.py        # Structured logging
    └── validators.py    # Input validation, security
```

## Google Drive Setup (Optional)

1. Create a folder in Google Drive
2. Add these files to the folder:
   - `system_prompt.md` - System prompt for the AI
   - `image_map.json` - Keyword-to-image mappings
   - `images/` subfolder - Image files referenced in image_map.json

3. Share the folder with your service account email
4. Configure `DRIVE_FOLDER_ID` in `.env`

### image_map.json Example

```json
{
  "mappings": [
    {"keyword": "architecture", "filename": "architecture.png", "file_id": "..."},
    {"keyword": "meme", "filename": "funny_cat.jpg", "file_id": "..."}
  ],
  "version": 1,
  "updated_at": "2026-01-07T12:00:00Z"
}
```

## API Endpoints

- `POST /webhook` - LINE webhook endpoint
- `GET /health` - Health check with service status

## Development

```bash
# Run with auto-reload (development only)
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# Run tests
pytest tests/
```

## License

MIT
