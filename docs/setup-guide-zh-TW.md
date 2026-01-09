# LINE Bot 環境設定教學

本教學說明如何取得 `.env` 檔案中所需的各項設定值。

---

## 1. LINE Channel 設定（必填）

### 取得 LINE_CHANNEL_SECRET 和 LINE_CHANNEL_ACCESS_TOKEN

1. **前往 LINE Developers Console**
   - 網址：https://developers.line.biz/console/
   - 使用您的 LINE 帳號登入

2. **建立 Provider（如果還沒有）**
   - 點擊「Create」按鈕
   - 輸入 Provider 名稱（例如：我的機器人）

3. **建立 Messaging API Channel**
   - 在 Provider 下點擊「Create a new channel」
   - 選擇「Messaging API」
   - 填寫以下資訊：
     - Channel name：機器人名稱
     - Channel description：機器人描述
     - Category：選擇適當類別
     - Subcategory：選擇子類別
   - 同意條款後點擊「Create」

4. **取得 Channel Secret**
   - 進入剛建立的 Channel
   - 點擊「Basic settings」分頁
   - 找到「Channel secret」
   - 點擊「Copy」複製
   - 貼到 `.env` 的 `LINE_CHANNEL_SECRET=` 後面

5. **取得 Channel Access Token**
   - 點擊「Messaging API」分頁
   - 往下找到「Channel access token (long-lived)」
   - 點擊「Issue」產生 Token
   - 複製產生的 Token
   - 貼到 `.env` 的 `LINE_CHANNEL_ACCESS_TOKEN=` 後面

6. **設定 Webhook URL**
   - 在「Messaging API」分頁找到「Webhook URL」
   - 點擊「Edit」
   - 輸入您的伺服器網址，例如：
     - 本地測試：使用 Cloudflare Tunnel 的網址
     - 正式環境：`https://your-domain.com/webhook`
   - 開啟「Use webhook」選項

---

## 2. Ollama 設定（必填）

### 取得 OLLAMA_BASE_URL

Ollama 是本機執行的 AI 模型服務。根據您的部署架構，有不同的設定方式：

### 情境 1：Ollama 和 Bot 在同一台電腦（最常見）

1. **安裝 Ollama**
   ```bash
   # Linux
   curl -fsSL https://ollama.com/install.sh | sh

   # macOS
   brew install ollama

   # Windows：從 https://ollama.com/download 下載安裝程式
   ```

2. **下載模型**
   ```bash
   # 下載推薦的 gemma3:4b 模型（約 2.5GB，適合 RTX 4080）
   ollama pull gemma3:4b

   # 或其他模型
   ollama pull llava:7b      # 較小的視覺模型
   ollama pull llava:13b     # 較大的視覺模型（需要更多 VRAM）
   ollama pull gemma2:9b     # 更大的文字模型
   ```

3. **啟動 Ollama 服務**
   ```bash
   ollama serve
   ```

4. **在 .env 設定**
   ```bash
   OLLAMA_BASE_URL=http://localhost:11434
   OLLAMA_MODEL=gemma3:4b
   ```

5. **測試連線**
   ```bash
   curl http://localhost:11434/api/tags
   # 應該列出已下載的模型
   ```

### 情境 2：Ollama 在區域網路的其他電腦

**適用場景**：Bot 在筆電上，Ollama 在有強大 GPU 的桌機上

**在 Ollama 伺服器上：**

1. **設定 Ollama 監聽所有網路介面**
   ```bash
   # Linux/macOS
   export OLLAMA_HOST=0.0.0.0:11434
   ollama serve

   # 或永久設定（Linux）
   echo 'OLLAMA_HOST=0.0.0.0:11434' | sudo tee -a /etc/environment
   sudo systemctl restart ollama
   ```

2. **取得伺服器 IP 位址**
   ```bash
   # Linux
   ip addr show | grep "inet "

   # macOS
   ifconfig | grep "inet "

   # Windows
   ipconfig
   ```
   例如：`192.168.1.100`

3. **設定防火牆允許連線**
   ```bash
   # Linux (ufw)
   sudo ufw allow 11434/tcp

   # Linux (firewalld)
   sudo firewall-cmd --permanent --add-port=11434/tcp
   sudo firewall-cmd --reload
   ```

**在 Bot 電腦上：**

1. **測試連線**
   ```bash
   curl http://192.168.1.100:11434/api/tags
   ```

2. **在 .env 設定**
   ```bash
   OLLAMA_BASE_URL=http://192.168.1.100:11434
   OLLAMA_MODEL=gemma3:4b
   ```

### 情境 3：Bot 在 Docker 容器中，Ollama 在主機上

**在 .env 設定**
```bash
# Linux/macOS
OLLAMA_BASE_URL=http://host.docker.internal:11434

# Windows
OLLAMA_BASE_URL=http://host.docker.internal:11434

# 或使用主機 IP
OLLAMA_BASE_URL=http://192.168.1.100:11434
```

### 情境 4：Ollama 和 Bot 都在 Docker 容器中

使用 Docker Compose：

**docker-compose.yml**
```yaml
version: '3.8'
services:
  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]

  linebot:
    build: .
    depends_on:
      - ollama
    environment:
      - OLLAMA_BASE_URL=http://ollama:11434
    ports:
      - "8000:8000"

volumes:
  ollama_data:
```

**在 .env 設定**
```bash
OLLAMA_BASE_URL=http://ollama:11434
```

### 驗證 Ollama 設定

執行以下測試確認設定正確：

```bash
# 測試基本連線
curl http://your-ollama-url:11434/api/tags

# 測試文字生成
curl http://your-ollama-url:11434/api/generate -d '{
  "model": "gemma3:4b",
  "prompt": "Say hello in Chinese",
  "stream": false
}'

# 測試視覺理解（需要 base64 編碼的圖片）
# 先取得測試圖片的 base64
base64 test_image.jpg > image_base64.txt

curl http://your-ollama-url:11434/api/generate -d "{
  \"model\": \"gemma3:4b\",
  \"prompt\": \"What is in this image?\",
  \"images\": [\"$(cat image_base64.txt)\"],
  \"stream\": false
}"
```

### 效能調整

**監控 GPU 使用**
```bash
# NVIDIA GPU
nvidia-smi

# 持續監控
watch -n 1 nvidia-smi
```

**如果遇到記憶體不足：**
- 使用較小的模型：`gemma3:4b` 而非 `llava:13b`
- 確保並發數為 1（已在程式中設定）
- 關閉其他使用 GPU 的程式

**調整 Ollama 設定（進階）**
```bash
# 限制 GPU 記憶體使用
export OLLAMA_NUM_GPU=1
export OLLAMA_GPU_OVERHEAD=0

# 設定模型並發數（預設 1，不建議改）
export OLLAMA_MAX_LOADED_MODELS=1
```

---

## 3. Google Drive 設定（選填）

> ⚠️ 這是選填項目。如果不設定，Bot 會使用預設的系統提示詞。

### 取得 GOOGLE_SERVICE_ACCOUNT_FILE 和 DRIVE_FOLDER_ID

1. **前往 Google Cloud Console**
   - 網址：https://console.cloud.google.com/
   - 登入您的 Google 帳號

2. **建立專案**
   - 點擊頂部的專案選擇器
   - 點擊「新增專案」
   - 輸入專案名稱（例如：LINE Bot）
   - 點擊「建立」

3. **啟用 Google Drive API**
   - 在左側選單選擇「API 和服務」→「程式庫」
   - 搜尋「Google Drive API」
   - 點擊進入後按「啟用」

4. **建立服務帳戶**
   - 選擇「API 和服務」→「憑證」
   - 點擊「建立憑證」→「服務帳戶」
   - 填寫服務帳戶名稱
   - 點擊「建立並繼續」
   - 角色選擇「檢視者」即可
   - 點擊「完成」

5. **下載金鑰檔案**
   - 點擊剛建立的服務帳戶
   - 選擇「金鑰」分頁
   - 點擊「新增金鑰」→「建立新金鑰」
   - 選擇「JSON」格式
   - 點擊「建立」會自動下載 JSON 檔案
   - 將檔案移到安全位置，例如：
     ```bash
     mv ~/Downloads/your-project-xxxxx.json /home/user/Desktop/Tom/AI-linebot/credentials.json
     ```
   - 在 `.env` 設定路徑：
     ```
     GOOGLE_SERVICE_ACCOUNT_FILE=/home/user/Desktop/Tom/AI-linebot/credentials.json
     ```

6. **建立 Google Drive 資料夾**
   - 前往 https://drive.google.com/
   - 建立新資料夾（例如：LineBot_Config）
   - 進入資料夾，從網址列複製資料夾 ID
     - 網址格式：`https://drive.google.com/drive/folders/XXXXX`
     - XXXXX 就是 DRIVE_FOLDER_ID
   - 在 `.env` 設定：
     ```
     DRIVE_FOLDER_ID=XXXXX
     ```

7. **分享資料夾給服務帳戶**
   - 在 Google Drive 的資料夾上按右鍵
   - 選擇「共用」
   - 輸入服務帳戶的 Email（在 JSON 檔案中的 `client_email`）
   - 權限設為「檢視者」
   - 點擊「完成」

8. **在資料夾中建立設定檔**
   - 建立 `system_prompt.md`：定義 Bot 的人格和行為
   - 建立 `image_map.json`：定義 `!img` 關鍵字對應的圖片
   - 建立 `images/` 資料夾：放置圖片檔案

---

## 範例 .env 檔案

```bash
# LINE Messaging API（必填）
LINE_CHANNEL_SECRET=abc123def456...
LINE_CHANNEL_ACCESS_TOKEN=eyJhbGciOiJIUzI1NiJ9...

# Ollama（必填）
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gemma3:4b

# Google Drive（選填）
GOOGLE_SERVICE_ACCOUNT_FILE=/path/to/credentials.json
DRIVE_FOLDER_ID=1A2B3C4D5E6F7G8H9I0J

# Admin 設定
ADMIN_USER_IDS=Uxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# 其他設定（使用預設值即可）
RATE_LIMIT_MAX_REQUESTS=30
QUEUE_MAX_SIZE=10
HOST=0.0.0.0
PORT=8000
LOG_LEVEL=INFO
```

---

## 4. Cloudflare Tunnel 設定（必填，用於公開 Webhook）

> 💡 LINE Webhook 必須使用 HTTPS，Cloudflare Tunnel 可以免費將本機服務暴露到網際網路

### 方法一：快速測試（使用免費臨時網域）

**最簡單的方式，適合測試和開發：**

1. **安裝 cloudflared**
   ```bash
   # Linux (Debian/Ubuntu)
   wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
   sudo dpkg -i cloudflared-linux-amd64.deb

   # macOS
   brew install cloudflared

   # Windows
   # 從 https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/ 下載
   ```

2. **啟動 Tunnel**
   ```bash
   cloudflared tunnel --url http://localhost:8000
   ```

3. **複製顯示的網址**
   ```
   +--------------------------------------------------------------------------------------------+
   |  Your quick Tunnel has been created! Visit it at:                                         |
   |  https://random-words-1234.trycloudflare.com                                              |
   +--------------------------------------------------------------------------------------------+
   ```

4. **設定 LINE Webhook URL**
   - 前往 LINE Developers Console → 您的頻道 → Messaging API
   - Webhook URL 設為：`https://random-words-1234.trycloudflare.com/webhook`
   - 啟用「Use webhook」

⚠️ **注意**：每次重啟 cloudflared，網址都會改變，需要重新設定 LINE Webhook

### 方法二：永久網域（需要自己的網域）

如果您有自己的網域（例如在 Cloudflare 管理），可以設定永久的 Tunnel：

1. **登入 Cloudflare**
   ```bash
   cloudflared tunnel login
   ```

2. **建立 Tunnel**
   ```bash
   cloudflared tunnel create linebot
   # 會產生 tunnel ID 和憑證檔案
   ```

3. **建立設定檔** `~/.cloudflared/config.yml`
   ```yaml
   tunnel: linebot
   credentials-file: /home/user/.cloudflared/<tunnel-id>.json

   ingress:
     - hostname: bot.yourdomain.com
       service: http://localhost:8000
     - service: http_status:404
   ```

4. **設定 DNS**
   ```bash
   cloudflared tunnel route dns linebot bot.yourdomain.com
   ```

5. **執行 Tunnel**
   ```bash
   cloudflared tunnel run linebot
   ```

6. **LINE Webhook URL** 設為：`https://bot.yourdomain.com/webhook`

### 方法三：使用 Docker Compose 一鍵部署（✨ 最推薦！）

**最方便的方式**，一個指令啟動所有服務（LINE Bot + Ollama + Cloudflare Tunnel）

**優點：**
- ✅ 所有服務自動啟動和連線
- ✅ 服務間網路自動設定
- ✅ 開機自動啟動（設定 `restart: unless-stopped`）
- ✅ 日誌統一管理
- ✅ 一鍵停止/重啟所有服務
- ✅ 不用擔心環境設定問題

**前置要求：**
```bash
# 1. 安裝 Docker 和 Docker Compose
# Ubuntu/Debian
sudo apt update
sudo apt install docker.io docker-compose

# macOS
brew install docker docker-compose

# 2. 安裝 nvidia-docker（如果使用 NVIDIA GPU）
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | \
  sudo tee /etc/apt/sources.list.d/nvidia-docker.list
sudo apt-get update && sudo apt-get install -y nvidia-docker2
sudo systemctl restart docker

# 3. 將自己加入 docker 群組（免 sudo）
sudo usermod -aG docker $USER
# 登出再登入使權限生效
```

**使用步驟：**

1. **專案已包含 `docker-compose.yml`**，檢查內容：
   ```bash
   cd /home/user/Desktop/Tom/AI-linebot
   cat docker-compose.yml
   ```

2. **設定 .env 檔案**
   ```bash
   cp .env.example .env
   nano .env
   ```

   **重要**：使用 Docker Compose 時，`OLLAMA_BASE_URL` 會自動設定，不用手動填寫

   只需填寫：
   - `LINE_CHANNEL_SECRET`
   - `LINE_CHANNEL_ACCESS_TOKEN`
   - `OLLAMA_MODEL=gemma3:4b`
   - （選填）Google Drive 相關設定

3. **一鍵啟動所有服務**
   ```bash
   docker-compose up -d
   ```
   這會自動啟動：
   - LINE Bot（port 8000）
   - Ollama（port 11434）
   - Cloudflare Tunnel（自動產生 HTTPS URL）

4. **查看 Cloudflare Tunnel 產生的 URL**
   ```bash
   docker-compose logs cloudflared | grep "https://"
   ```
   或即時查看：
   ```bash
   docker-compose logs -f cloudflared
   ```

   輸出範例：
   ```
   cloudflared  | +--------------------------------------------------------------------------------------------+
   cloudflared  | |  Your quick Tunnel has been created! Visit it at:                                         |
   cloudflared  | |  https://random-words-1234.trycloudflare.com                                              |
   cloudflared  | +--------------------------------------------------------------------------------------------+
   ```

5. **設定 LINE Webhook**
   - 複製上面的 URL（例如：`https://random-words-1234.trycloudflare.com`）
   - 前往 LINE Developers Console → 您的頻道 → Messaging API
   - Webhook URL 設為：`https://random-words-1234.trycloudflare.com/webhook`
   - 啟用「Use webhook」

6. **下載 Ollama 模型（首次使用）**
   ```bash
   docker-compose exec ollama ollama pull gemma3:4b

   # 查看已下載的模型
   docker-compose exec ollama ollama list
   ```

**常用管理指令：**

```bash
# 查看所有服務狀態
docker-compose ps

# 查看所有服務日誌（即時）
docker-compose logs -f

# 查看特定服務日誌
docker-compose logs -f linebot      # LINE Bot 日誌
docker-compose logs -f cloudflared  # Cloudflare Tunnel URL
docker-compose logs -f ollama       # Ollama 日誌

# 重啟所有服務
docker-compose restart

# 重啟特定服務
docker-compose restart linebot

# 停止所有服務（保留資料）
docker-compose down

# 停止並刪除所有資料（重新開始）
docker-compose down -v

# 更新程式碼後重新建置
docker-compose up -d --build

# 進入容器內部（除錯用）
docker-compose exec linebot /bin/bash
docker-compose exec ollama /bin/bash
```

**設定開機自動啟動：**

Docker Compose 服務已設定 `restart: unless-stopped`，只要 Docker 開機自動啟動即可：

```bash
# 設定 Docker 開機自動啟動
sudo systemctl enable docker

# 現在每次開機後，docker-compose 的所有服務會自動啟動
```

**如果使用 Google Drive（需要掛載金鑰檔）：**

1. 將服務帳號金鑰放在 `credentials` 資料夾：
   ```bash
   mkdir -p /home/user/Desktop/Tom/AI-linebot/credentials
   mv ~/Downloads/your-service-account.json /home/user/Desktop/Tom/AI-linebot/credentials/service_account.json
   ```

2. 在 `.env` 設定（路徑相對於容器內部）：
   ```bash
   GOOGLE_SERVICE_ACCOUNT_FILE=/app/credentials/service_account.json
   DRIVE_FOLDER_ID=your_folder_id_here
   ```

3. `docker-compose.yml` 已自動掛載 `./credentials` 到容器

**監控 GPU 使用（如果使用 GPU）：**

```bash
# 在主機上監控
watch -n 1 nvidia-smi

# 或在 Ollama 容器內監控
docker-compose exec ollama nvidia-smi
```

**故障排除：**

```bash
# 檢查容器是否在運行
docker-compose ps

# 檢查特定服務的錯誤
docker-compose logs linebot --tail=50
docker-compose logs ollama --tail=50

# 重新建置並啟動（當程式碼有更新時）
docker-compose down
docker-compose up -d --build

# 檢查網路連線
docker-compose exec linebot curl http://ollama:11434/api/tags
```

**優點總結：**
- ✅ **一個指令**啟動所有服務
- ✅ **自動管理**服務依賴和網路
- ✅ **隔離環境**不污染主機
- ✅ **簡化部署**適合生產環境
- ✅ **統一管理**日誌和監控

### 方法四：使用 systemd 背景執行（傳統方式）

讓 Cloudflare Tunnel 開機自動啟動：

1. **建立 systemd 服務檔** `/etc/systemd/system/cloudflared.service`
   ```ini
   [Unit]
   Description=Cloudflare Tunnel
   After=network.target

   [Service]
   Type=simple
   User=your-username
   ExecStart=/usr/bin/cloudflared tunnel --url http://localhost:8000
   Restart=always
   RestartSec=10

   [Install]
   WantedBy=multi-user.target
   ```

2. **啟用並啟動服務**
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable cloudflared
   sudo systemctl start cloudflared

   # 查看狀態和 URL
   sudo systemctl status cloudflared
   sudo journalctl -u cloudflared -f
   ```

### 驗證 Tunnel 連線

測試 Tunnel 是否正常運作：

```bash
# 測試 health endpoint
curl https://your-tunnel-url/health

# 應該回傳：
# {"status":"healthy","services":{...}}
```

---

## 5. 完整部署流程

### 步驟 1：準備環境

```bash
# 進入專案目錄
cd /home/user/Desktop/Tom/AI-linebot

# 建立虛擬環境（如果還沒有）
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安裝相依套件
pip install -r requirements.txt

# 設定環境變數
cp .env.example .env
nano .env  # 填入所有必要的設定值
```

### 步驟 2：啟動所有服務

**開啟 3 個終端機視窗：**

**終端機 1 - Ollama 服務：**
```bash
ollama serve
```

**終端機 2 - LINE Bot 主程式：**
```bash
cd /home/user/Desktop/Tom/AI-linebot
source venv/bin/activate
python main.py
```

**終端機 3 - Cloudflare Tunnel：**
```bash
cloudflared tunnel --url http://localhost:8000
# 複製顯示的 URL 並設定到 LINE Webhook
```

### 步驟 3：設定 LINE Webhook

1. 從終端機 3 複製 Cloudflare Tunnel 的 URL
2. 前往 LINE Developers Console
3. 設定 Webhook URL：`https://your-tunnel-url/webhook`
4. 啟用 Webhook

### 步驟 4：測試機器人

在 LINE 群組中測試：

```
!hej 你好
!hej 台灣的首都是哪裡？
```

測試圖片分析（多模態）：
1. 上傳一張圖片到群組
2. 回覆該圖片：`!hej 這張圖片裡有什麼？`

測試配置重載（如果有設定 Google Drive）：
```
!reload
```

---

## 測試連線

設定完成後，執行以下指令測試：

```bash
# 啟動服務
cd /home/user/Desktop/Tom/AI-linebot
source venv/bin/activate
python main.py
```

如果看到以下訊息表示啟動成功：
```
✅ Ollama service is available
✅ Queue worker started
🚀 Server ready on 0.0.0.0:8000
```

---

## 常見問題

### Q: LINE Webhook 驗證失敗？
A: 確認 Webhook URL 是 HTTPS 且可以公開存取。本地開發請使用 Cloudflare Tunnel。

### Q: Ollama 連不上？
A: 執行 `ollama serve` 啟動服務，並確認防火牆沒有擋住 11434 port。

### Q: Google Drive 無法同步？
A: 確認服務帳戶有資料夾的檢視權限，且 JSON 金鑰檔案路徑正確。

---

## 需要幫助？

如有問題，請檢查：
1. 所有必填欄位都已填寫
2. LINE Channel 的 Webhook 已開啟
3. Ollama 服務正在運作
4. 網路連線正常
