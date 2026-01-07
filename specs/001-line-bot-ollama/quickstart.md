# Quickstart Guide: LINE Bot with Local Ollama VLM Integration

**Feature**: [spec.md](./spec.md) | **Phase**: 1 (Design) | **Date**: 2026-01-07

## Purpose

This guide provides step-by-step instructions for setting up, configuring, and deploying the LINE Bot system with local Ollama VLM integration as a constantly-running headless backend service. No frontend or web interface required - all interaction happens through LINE messages.

**Execution Model**:
1. FastAPI server starts → `@app.on_event("startup")` triggers
2. Background workers launch (LLM queue processor, Drive sync poller) → run forever
3. LINE webhook receives events → enqueues tasks → returns HTTP 200 immediately
4. Workers process tasks → reply to LINE → loop back to waiting
5. Service never stops (runs as systemd daemon)

---

## Prerequisites

### Hardware Requirements
- ✅ NVIDIA GPU with 12GB+ VRAM (RTX 4080 or equivalent)
- ✅ 16GB+ system RAM
- ✅ 50GB+ free disk space (for model and cache)
- ✅ Linux operating system (Ubuntu 20.04+ recommended)

### Software Requirements
- ✅ Python 3.11 or higher
- ✅ NVIDIA drivers (version 525+ for CUDA 12)
- ✅ Git
- ✅ Conda (Miniconda or Anaconda)
- ✅ Ollama (installation instructions below)

### Account Setup
- ✅ LINE Developer Account with Messaging API channel created
- ✅ Google Cloud Project with Drive API enabled
- ✅ Service account created with JSON credentials downloaded

---

## Step 1: Install Ollama and Download Model

### 1.1 Install Ollama

```bash
# Download and install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Verify installation
ollama --version
```

### 1.2 Download gemma3:4b Model

```bash
# Pull the model (this will take several minutes)
ollama pull gemma3:4b

# Verify model is available
ollama list

# Test model
ollama run gemma3:4b "What is 2+2?"
```

**Expected Output**:
```
NAME            ID              SIZE      MODIFIED
gemma3:4b       a1b2c3d4e5f6    4.2 GB    2 minutes ago
```

### 1.3 Start Ollama Service

```bash
# Start Ollama server (runs in background)
ollama serve

# Or use systemd service
sudo systemctl enable ollama
sudo systemctl start ollama
sudo systemctl status ollama
```

**Verify Service**:
```bash
curl http://localhost:11434/api/tags
```

---

## Step 2: Set Up Google Drive

### 2.1 Create Folder Structure

1. Open Google Drive in browser
2. Create a new folder: `LINE Bot Config`
3. Inside this folder, create:
   - `system_prompt.md` (text file)
   - `image_map.json` (JSON file)
   - `images/` (subfolder)

**Example folder structure**:
```
LINE Bot Config/
├── system_prompt.md
├── image_map.json
└── images/
    └── (empty for now)
```

### 2.2 Create system_prompt.md

Create a new file `system_prompt.md` with this content:

```markdown
You are a helpful assistant in a LINE group chat.

Guidelines:
- Respond concisely (1-3 sentences preferred)
- Use Traditional Chinese when user writes in Chinese
- Use English when user writes in English
- Be friendly and conversational
- If you don't know something, admit it honestly
```

### 2.3 Create image_map.json

Create a new file `image_map.json` with this content:

```json
{
  "version": 1,
  "updated_at": "2026-01-07T10:00:00Z",
  "mappings": []
}
```

### 2.4 Share Folder with Service Account

1. Right-click on `LINE Bot Config` folder
2. Click "Share"
3. Paste your service account email (e.g., `linebot@project-id.iam.gserviceaccount.com`)
4. Set permission to "Viewer"
5. Click "Send"

### 2.5 Get Folder ID

1. Open the `LINE Bot Config` folder in browser
2. Copy the folder ID from the URL:
   ```
   https://drive.google.com/drive/folders/1aBcDeFgHiJkLmNoPqRsTuVwXyZ
                                            ^^^^^^^^^^^^^^^^^^^^^^^^^^
                                            This is your folder ID
   ```
3. Save this ID for later (you'll add it to `.env` file)

---

## Step 3: Set Up LINE Messaging API

### 3.1 Create LINE Channel

1. Go to [LINE Developers Console](https://developers.line.biz/console/)
2. Create a new provider (or use existing)
3. Create a new Messaging API channel
4. Fill in required information:
   - Channel name: "LINE Bot with Ollama"
   - Channel description: "AI-powered chatbot"
   - Category: Choose appropriate category

### 3.2 Get Channel Credentials

After creating the channel:

1. Go to "Basic settings" tab
   - Copy **Channel Secret**
2. Go to "Messaging API" tab
   - Issue **Channel Access Token** (long-lived)
   - Copy the token

**Save these values** - you'll need them in Step 5.

### 3.3 Configure Channel Settings

In "Messaging API" tab:

1. **Webhook settings**:
   - ⚠️ Leave blank for now (we'll update this after Cloudflare Tunnel setup)
   - Enable "Use webhook"
2. **Response settings**:
   - Disable "Auto-reply messages"
   - Disable "Greeting messages"
3. **Bot settings**:
   - Enable "Allow bot to join group chats"

---

## Step 4: Clone and Configure Project

### 4.1 Clone Repository

```bash
# Navigate to desired directory
cd ~/Desktop/Tom

# Clone repository
git clone <repository-url> AI-linebot
cd AI-linebot

# Checkout feature branch
git checkout 001-line-bot-ollama
```

### 4.2 Set Up Python Environment

```bash
# Create virtual environment
python3.11 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt
```

**Expected dependencies** (from `requirements.txt`):
```
fastapi==0.104.1
uvicorn[standard]==0.24.0
line-bot-sdk==3.6.0
ollama-python==0.1.5  # Or use aiohttp directly
google-api-python-client==2.108.0
google-auth==2.23.4
google-auth-oauthlib==1.1.0
Pillow==10.1.0
pydantic==2.5.0
python-dotenv==1.0.0
aiohttp==3.9.0
pytest==7.4.3
pytest-asyncio==0.21.1
```

### 4.3 Create Environment Configuration

```bash
# Copy example environment file
cp .env.example .env

# Edit with your favorite editor
nano .env
```

**Fill in `.env` with your credentials**:
```bash
# LINE Messaging API
LINE_CHANNEL_SECRET=your_channel_secret_here
LINE_CHANNEL_ACCESS_TOKEN=your_channel_access_token_here

# Google Drive
GOOGLE_DRIVE_FOLDER_ID=1aBcDeFgHiJkLmNoPqRsTuVwXyZ
GOOGLE_SERVICE_ACCOUNT_FILE=/home/user/Desktop/Tom/AI-linebot/service_account_key.json

# Ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gemma3:4b
OLLAMA_TIMEOUT_TEXT=10
OLLAMA_TIMEOUT_MULTIMODAL=30

# Queue Configuration
QUEUE_MAX_SIZE=10
QUEUE_CONCURRENCY=1

# Rate Limiting
RATE_LIMIT_MAX_REQUESTS=30
RATE_LIMIT_WINDOW_SECONDS=60

# Admin Notifications (LINE user IDs, comma-separated)
ADMIN_USER_IDS=U1234567890abcdef1234567890abcdef,U9876543210fedcba9876543210fedcba

# Cache
CACHE_DIR=/tmp/linebot_cache
CACHE_MAX_SIZE_MB=100

# Sync Settings
DRIVE_SYNC_INTERVAL_SECONDS=30

# Application
DEBUG=False
LOG_LEVEL=INFO
```

### 4.4 Add Service Account Credentials

1. Download service account JSON key from Google Cloud Console
2. Save it in project root as `service_account_key.json`
3. **IMPORTANT**: Add to `.gitignore` to prevent committing secrets

```bash
# Verify file exists
ls -l service_account_key.json

# Add to .gitignore
echo "service_account_key.json" >> .gitignore
```

---

## Step 5: Set Up Cloudflare Tunnel

### 5.1 Install cloudflared

```bash
# Download latest release
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb

# Install
sudo dpkg -i cloudflared-linux-amd64.deb

# Verify installation
cloudflared --version
```

### 5.2 Authenticate with Cloudflare

```bash
# Login to Cloudflare (opens browser)
cloudflared tunnel login

# This will open a browser window - log in and authorize
```

### 5.3 Create Tunnel

```bash
# Create a new tunnel
cloudflared tunnel create linebot-tunnel

# This creates a credentials file at:
# ~/.cloudflared/<tunnel-id>.json

# List tunnels to verify
cloudflared tunnel list
```

### 5.4 Configure Tunnel

Create tunnel configuration file:

```bash
mkdir -p ~/.cloudflared
nano ~/.cloudflared/config.yml
```

**Add this configuration**:
```yaml
tunnel: linebot-tunnel
credentials-file: /home/user/.cloudflared/<tunnel-id>.json

ingress:
  - hostname: linebot.yourdomain.com  # Replace with your domain
    service: http://localhost:8000
  - service: http_status:404
```

### 5.5 Create DNS Record

```bash
# Route DNS to tunnel (replace with your domain)
cloudflared tunnel route dns linebot-tunnel linebot.yourdomain.com
```

**Alternatively**: Manually add CNAME record in Cloudflare dashboard:
- Name: `linebot`
- Target: `<tunnel-id>.cfargotunnel.com`

### 5.6 Start Tunnel

```bash
# Run tunnel in background
cloudflared tunnel run linebot-tunnel &

# Or use systemd service for auto-start
sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
```

**Verify tunnel**:
```bash
curl https://linebot.yourdomain.com
# Should return 404 (FastAPI not running yet, this is expected)
```

---

## Step 6: Run the Bot

### 6.1 Start FastAPI Server

```bash
# Activate virtual environment
source venv/bin/activate

# Run with uvicorn
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload

# Or run in production mode (no auto-reload)
uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 1
```

**Expected output**:
```
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Background workers started (LLM queue processor, Drive sync)
INFO:     LLM worker ready and waiting for tasks
INFO:     Drive sync worker started (polling every 30s)
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

**What happens on startup**:
1. FastAPI loads configuration from `.env`
2. `@app.on_event("startup")` executes
3. `asyncio.create_task(llm_worker())` → Worker enters infinite loop waiting at `await queue.get()`
4. `asyncio.create_task(drive_sync_worker())` → Starts polling Google Drive every 30s
5. Server ready to receive LINE webhooks
6. **Workers never exit** - they run continuously until you stop the service

### 6.2 Verify Health Check

In another terminal:
```bash
# Test health endpoint
curl http://localhost:8000/health

# Expected response
{"status":"ok","ollama":"available","drive":"connected"}
```

### 6.3 Update LINE Webhook URL

1. Go to LINE Developers Console
2. Navigate to your channel's "Messaging API" tab
3. Update webhook URL to: `https://linebot.yourdomain.com/webhook`
4. Click "Verify" - should show success
5. Enable "Use webhook"

---

## Step 7: Test the Bot

### 7.1 Add Bot to LINE Group

1. Go to LINE Developers Console
2. Find your bot's QR code or add by ID
3. Add the bot to a LINE group
4. Bot should join automatically (if settings are correct)

### 7.2 Test Commands

**Test 1: Simple text question**
```
In LINE group, send:
!hej What is the capital of France?

Expected response:
Paris is the capital of France.
```

**Test 2: Reply to text message**
```
1. Someone posts: "The sky is blue"
2. You reply to that message with: !hej Summarize this
Expected response:
The message states that the sky is blue.
```

**Test 3: Image analysis**
```
1. Someone posts an image of a cat
2. You reply to that image with: !hej What's in this image?
Expected response:
The image shows a cat [description details]...
```

**Test 4: Image retrieval** (after adding images to Drive)
```
1. Add an image to Google Drive images/ folder
2. Update image_map.json with keyword mapping
3. Wait 60 seconds for auto-sync
4. Send: !img <keyword>
Expected response:
[Bot sends the image]
```

**Test 5: Manual reload**
```
1. Edit system_prompt.md in Google Drive
2. Send in LINE: !reload
Expected response:
✅ 設定已重新載入 (Config reloaded)
```

### 7.3 Verify Logs

Check FastAPI logs for the execution flow:
```
INFO: Received webhook event from user U4af4980629...
INFO: Command detected: !hej "What is the capital of France?"
INFO: Enqueued task to LLM queue (queue size: 1/10)
INFO: [Webhook] Returned HTTP 200 to LINE (response time: 45ms)
INFO: [LLM Worker] Dequeued request, acquiring semaphore...
INFO: [LLM Worker] Semaphore acquired, calling Ollama API (text-only)
INFO: [LLM Worker] Ollama response received in 2.3s
INFO: [LLM Worker] Sent reply to LINE group
INFO: [LLM Worker] Task complete, back to waiting for next task...
```

**Key observations**:
- Webhook responds in <100ms (just enqueues and returns)
- Worker processes task independently
- Worker logs "back to waiting" → enters `await queue.get()` sleep state
- Next webhook event will wake worker immediately

---

## Step 8: Monitoring and Maintenance

### 8.1 Log Files

Set up log rotation:
```bash
# Configure logging in src/utils/logger.py
# Logs written to: /var/log/linebot/app.log

# Rotate logs daily
sudo nano /etc/logrotate.d/linebot
```

**Logrotate config**:
```
/var/log/linebot/*.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
    create 0644 user user
}
```

### 8.2 Systemd Service (Production)

Create service file for auto-start:
```bash
sudo nano /etc/systemd/system/linebot.service
```

**Service configuration**:
```ini
[Unit]
Description=LINE Bot with Ollama VLM
After=network.target ollama.service

[Service]
Type=simple
User=user
WorkingDirectory=/home/user/Desktop/Tom/AI-linebot
Environment="PATH=/home/user/Desktop/Tom/AI-linebot/venv/bin"
ExecStart=/home/user/Desktop/Tom/AI-linebot/venv/bin/uvicorn src.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Enable and start service**:
```bash
sudo systemctl daemon-reload
sudo systemctl enable linebot
sudo systemctl start linebot
sudo systemctl status linebot
```

### 8.3 Health Monitoring

Set up cron job to check health:
```bash
crontab -e
```

**Add health check**:
```bash
# Check every 5 minutes
*/5 * * * * curl -f http://localhost:8000/health || echo "Bot health check failed" | mail -s "LINE Bot Alert" admin@example.com
```

---

## Troubleshooting

### Issue 1: Ollama Service Not Running

**Symptoms**: Bot returns "AI service temporarily unavailable"

**Solution**:
```bash
# Check Ollama status
sudo systemctl status ollama

# Restart if needed
sudo systemctl restart ollama

# Verify model available
ollama list
```

### Issue 2: Webhook Signature Validation Failed

**Symptoms**: LINE webhook returns 403 Forbidden

**Solution**:
```bash
# Verify channel secret in .env matches LINE console
echo $LINE_CHANNEL_SECRET

# Check logs for signature mismatch details
tail -f /var/log/linebot/app.log
```

### Issue 3: Google Drive Sync Failing

**Symptoms**: Logs show "Drive API error"

**Solution**:
```bash
# Verify service account credentials
cat service_account_key.json | jq .

# Test Drive API manually
python3 -c "
from google.oauth2 import service_account
from googleapiclient.discovery import build
creds = service_account.Credentials.from_service_account_file('service_account_key.json')
service = build('drive', 'v3', credentials=creds)
print(service.files().list(pageSize=1).execute())
"
```

### Issue 4: Queue Overflow

**Symptoms**: Users receive "系統忙碌中" messages frequently

**Solution**:
```bash
# Check queue metrics in logs
grep "queue size" /var/log/linebot/app.log

# Consider increasing QUEUE_MAX_SIZE in .env (trade-off: longer wait times)
# Or optimize Ollama parameters for faster inference
```

### Issue 5: Cloudflare Tunnel Disconnected

**Symptoms**: LINE webhook verification fails

**Solution**:
```bash
# Check tunnel status
cloudflared tunnel info linebot-tunnel

# Restart tunnel
sudo systemctl restart cloudflared

# Verify tunnel connectivity
curl https://linebot.yourdomain.com/health
```

---

## Next Steps

✅ **Quickstart Complete** - Bot is now operational!

**Recommended Next Steps**:
1. Add more images to Google Drive for `!img` command
2. Customize `system_prompt.md` for your use case
3. Set up monitoring alerts for admins
4. Run `/speckit.tasks` to generate implementation task breakdown
5. Implement additional features (conversation history, user preferences, etc.)

**Performance Tuning**:
- Adjust `OLLAMA_TIMEOUT_*` values based on observed latency
- Monitor GPU usage with `nvidia-smi`
- Optimize `temperature` and `top_p` in Ollama requests for desired creativity level

**Security Hardening**:
- Rotate service account credentials regularly
- Implement IP whitelisting for webhook endpoint
- Enable rate limiting at Cloudflare level
- Review logs for suspicious activity

---

## Support and Resources

- **LINE Messaging API Docs**: https://developers.line.biz/en/docs/messaging-api/
- **Ollama Documentation**: https://github.com/ollama/ollama/blob/main/docs/api.md
- **Google Drive API Reference**: https://developers.google.com/drive/api/v3/reference
- **FastAPI Documentation**: https://fastapi.tiangolo.com/
- **Cloudflare Tunnel Guide**: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/

**Project Documentation**:
- [Feature Specification](./spec.md)
- [Implementation Plan](./plan.md)
- [Data Models](./data-model.md)
- [API Contracts](./contracts/)
- [Research Findings](./research.md)
