# LINE Bot with Ollama - 完整使用指南

>  本地部署的 LINE 聊天機器人，整合 Ollama VLM（視覺語言模型）

---

## 目錄

1. [快速啟動](#快速啟動)
2. [獲取 Webhook URL](#獲取-webhook-url)
3. [設定 LINE Webhook](#設定-line-webhook)
4. [測試機器人](#測試機器人)
5. [Bot 指令說明](#bot-指令說明)
6. [常用管理指令](#常用管理指令)
7. [常見問題](#常見問題)
8. [進階設定](#進階設定)

---

## 快速啟動
### 手動啟動

```bash
# 1. 啟動所有服務
docker compose up -d

# 2. 檢查服務狀態
docker compose ps

docker compose down && docker compose up -d
docker compose down && docker compose up -d --build

# restart linebot
docker compose build linebot && docker compose up -d linebot

# webhook url
docker logs cloudflared 2>&1 | grep -o 'https://[a-zA-Z0-9-]*\.trycloudflare\.com' | head -1

# linebot log search group_id
docker compose logs --tail=500 linebot | grep -E "(group_id|groupId|Full event structure)"
docker compose logs linebot | grep -o '"groupId": "[^"]*"' | sort -u
```

應該看到三個服務都在運行：
- `ollama` - AI 模型服務（使用 GPU）
- `linebot` - LINE Bot 主服務
- `cloudflared` - Cloudflare Tunnel

### 首次使用：下載 AI 模型

```bash
# 檢查模型是否已下載
docker compose exec ollama ollama list

# 下載模型（根據硬體二選一，改 .env 的 OLLAMA_MODEL 對應）：
docker compose exec ollama ollama pull qwen3.5:35b-a3b  # 高品質（約 20GB，需要 32GB RAM）
# docker compose exec ollama ollama pull qwen3.5:9b     # 快速（約 5GB，12GB VRAM 可全載入）

# 更新 ollama
docker pull ollama/ollama:latest
docker compose down ollama && docker compose up -d ollama
```

---

## 獲取 Webhook URL

### 方法一：使用腳本（推薦）

```bash
./get-url.sh
```

輸出範例：
```
 Webhook URL:

  https://xxxxx-xxxxx-1234.trycloudflare.com/webhook

請將此 URL 設定到 LINE Developers Console
```

### 方法二：手動查看

```bash
docker logs cloudflared 2>&1 | grep -o 'https://[a-zA-Z0-9-]*\.trycloudflare\.com' | head -1
```

**重要：每次重啟 Cloudflare Tunnel，URL 可能會改變！**

### 重要：設定 PUBLIC_BASE_URL（!img 指令必需）

如果要使用 `!img` 指令發送圖片，必須設定 `PUBLIC_BASE_URL`：

```bash
# 1. 獲取 Cloudflare Tunnel URL
TUNNEL_URL=$(docker logs cloudflared 2>&1 | grep -o 'https://[a-zA-Z0-9-]*\.trycloudflare\.com' | head -1)

# 2. 在 .env 文件中設定 PUBLIC_BASE_URL
echo "PUBLIC_BASE_URL=$TUNNEL_URL" >> .env

# 3. 重啟服務讓設定生效
docker compose restart linebot
```

或者手動編輯 `.env` 文件，將獲取到的 URL 設定為 `PUBLIC_BASE_URL`：

```bash
PUBLIC_BASE_URL=https://xxxxx-xxxxx-1234.trycloudflare.com
```

**注意：** Cloudflare Tunnel URL 改變時，需要重新設定 PUBLIC_BASE_URL

---

## 設定 LINE Webhook

1. 前往 [LINE Developers Console](https://developers.line.biz/console/)
2. 選擇你的頻道 → **Messaging API**
3. 找到 **Webhook settings**
4. **Webhook URL** 填入：`https://xxxxx.trycloudflare.com/webhook`
5. 點選 **Verify**（應該顯示成功）
6. 啟用 **Use webhook**
7. 關閉 **Auto-reply messages**（在 LINE Official Account Manager 中）

---

## 測試機器人

### 基本測試

在 LINE 群組或 1 對 1 聊天中輸入：

```
!hej 你好
```

機器人應該會回應！

### 進階測試

```
!hej 台灣的首都是哪裡？
!hej 用繁體中文寫一首詩
!hej 解釋什麼是機器學習
```

---

## Bot 指令說明

### 1. !hej [問題]

向 AI 提問

**範例：**
```
!hej 你好
!hej 台灣有哪些著名景點？
!hej 請用 Python 寫一個斐波那契數列
```

### 2. !hej（回覆圖片）

分析圖片內容（多模態 VLM）

**使用方法：**
1. 在 LINE 上傳一張圖片
2. **回覆該圖片**並輸入：`!hej 這張圖片裡有什麼？`
3. AI 會分析並描述圖片內容

**範例：**
- `!hej 請描述這張圖片`
- `!hej 圖片中的人在做什麼？`
- `!hej 這是什麼建築物？`

### 3. !hej（回覆訊息）

引用之前的訊息作為上下文

**使用方法：**
1. **回覆某則訊息**
2. 輸入：`!hej 請幫我總結這段內容`
3. AI 會使用被回覆的訊息作為上下文

### 4. !img [關鍵字]

發送預設的圖片（需要設定 Google Drive）

**範例：**
```
!img 架構圖
!img meme
```

### 5. !reload

重新載入設定（從 Google Drive 同步，需要設定 Google Drive）

---

## 常用管理指令

### 測試系統

```bash
# 執行完整系統測試
./test_webhook.sh
```

這會測試：
- 服務狀態
- 健康檢查端點
- Ollama 連接
- Cloudflare Tunnel URL
- 公開訪問

### 查看日誌

```bash
# 查看所有服務日誌
docker compose logs -f

# 只查看 LINE Bot 日誌
docker compose logs -f linebot

# 只查看 Ollama 日誌
docker compose logs -f ollama

# 只查看 Cloudflare Tunnel 日誌
docker compose logs -f cloudflared
```

### 重啟服務

```bash
# 重啟所有服務
docker compose restart

# 重啟特定服務
docker compose restart linebot     # 重啟 Bot
docker compose restart ollama      # 重啟 Ollama
docker compose restart cloudflared # 重啟 Tunnel
```

### 停止服務

```bash
# 停止所有服務
docker compose down

# 停止並刪除所有資料
docker compose down -v
```

### 監控

```bash
# 檢查服務狀態
docker compose ps

# 檢查健康狀態
curl http://localhost:8000/health | python3 -m json.tool

# 檢查 GPU 使用情況
nvidia-smi

# 即時監控 GPU
watch -n 1 nvidia-smi

# 查看資源使用
docker stats

# 查看所有排程任務和下次執行時間
curl -s http://localhost:8000/health | jq '.services.scheduler'

# 實時查看所有訊息的上下文
docker compose logs -f linebot | grep "Current context"

# 查看 LLM 請求時的完整上下文
docker compose logs -f linebot | grep "Conversation history"

```

---

## 常見問題

### Q1: 機器人沒有回應？

**檢查清單：**

1. **確認服務正在運行**
   ```bash
   docker compose ps
   ```
   所有服務應該顯示 `Up`

2. **查看 LINE Bot 日誌**
   ```bash
   docker compose logs -f linebot
   ```
   看看是否有錯誤訊息

3. **確認 Webhook URL 正確**
   ```bash
   ./get-url.sh
   ```
   確認 LINE Developers Console 中的 URL 與此相同

4. **確認 LINE Webhook 已啟用**
   - 在 LINE Developers Console 檢查 **Use webhook** 是否開啟
   - 確認 **Auto-reply messages** 已關閉

5. **測試 Webhook 連通性**
   ```bash
   # 在 LINE Console 點擊 Verify 按鈕
   ```

### Q2: Cloudflare URL 改變了怎麼辦？

臨時 Tunnel 的 URL 每次重啟會改變。

**解決方法：**

1. **不要停止服務**：使用 `docker compose restart` 而不是 `down` 再 `up`

2. **重新設定 Webhook**：
   ```bash
   ./get-url.sh
   ```
   然後更新 LINE Webhook URL

3. **使用永久 Tunnel**（進階）：
   參考[進階設定](#使用永久-cloudflare-tunnel)

### Q3: Ollama 模型下載失敗或太慢？

```bash
# 檢查網路連線
docker compose exec ollama ping -c 3 google.com

# 重試下載（替換為目前 .env 中設定的模型名稱）
docker compose exec ollama ollama pull qwen3.5:35b-a3b  # or qwen3.5:9b

# 查看下載進度
docker compose logs -f ollama
```

### Q4: Ollama 推理速度很慢？

**檢查 GPU 是否正常工作：**

```bash
# 查看 Ollama 是否使用 GPU
docker compose logs ollama | grep GPU

# 確認 GPU 可見
docker compose exec ollama nvidia-smi
```

應該看到 RTX 4080 被檢測到。

**如果沒有 GPU：**
- 檢查 `nvidia-docker` 是否安裝
- 確認 `docker-compose.yml` 中的 GPU 設定正確

### Q5: GPU 記憶體不足？

如果你的 GPU 記憶體較小，可以：

1. **使用更小的模型**：
   ```bash
   # 在 .env 中修改（只改這一行即可）
   OLLAMA_MODEL=qwen3.5:35b-a3b  # 高品質（慢），or OLLAMA_MODEL=qwen3.5:9b 快速（輕量）

   # 下載對應模型
   docker compose exec ollama ollama pull qwen3.5:35b-a3b
   # docker compose exec ollama ollama pull qwen3.5:9b

   # 重啟服務
   docker compose restart linebot
   ```

2. **或使用 CPU 模式**：
   - 編輯 `docker compose.yml`
   - 移除 `deploy.resources.reservations` 部分

### Q6: 如何查看當前使用的模型？

```bash
# 列出所有已下載的模型
docker compose exec ollama ollama list

# 測試模型推理（使用目前 .env 中設定的模型）
docker compose exec ollama ollama run qwen3.5:35b-a3b "Hello"  # or qwen3.5:9b
```

### Q7: 如何完全重置？

```bash
# 停止並刪除所有容器和資料
docker compose down -v

# 重新啟動
./start.sh

# 重新下載模型
docker compose exec ollama ollama pull qwen3.5:35b-a3b  # or qwen3.5:9b
```

### Q8: LINE 收到訊息但機器人回覆「Error, try again」？

這通常表示 Ollama 推理失敗。檢查：

```bash
# 查看 Ollama 日誌
docker compose logs -f ollama

# 查看 LINE Bot 日誌
docker compose logs -f linebot

# 測試 Ollama 是否正常（使用目前 .env 中設定的模型）
docker compose exec ollama ollama run qwen3.5:35b-a3b "測試"  # or qwen3.5:9b
```

### Q9: !img 指令無法發送圖片？

**症狀：** 使用 `!img 關鍵字` 後，收到「找到圖片」的訊息但沒有實際收到圖片

**原因：** 沒有設定 `PUBLIC_BASE_URL`，LINE 無法透過 HTTPS URL 下載圖片

**解決方法：**

1. **獲取 Cloudflare Tunnel URL**
   ```bash
   docker logs cloudflared 2>&1 | grep -o 'https://[a-zA-Z0-9-]*\.trycloudflare\.com' | head -1
   ```

2. **在 .env 中設定 PUBLIC_BASE_URL**
   ```bash
   # 編輯 .env 文件
   nano .env

   # 加入或更新這一行（替換成你的 Tunnel URL）
   PUBLIC_BASE_URL=https://xxxxx-xxxxx-1234.trycloudflare.com
   ```

3. **重啟服務**
   ```bash
   docker compose restart linebot
   ```

4. **驗證設定**
   ```bash
   # 查看日誌確認 PUBLIC_BASE_URL 被讀取
   docker compose logs linebot | grep "PUBLIC_BASE_URL"
   ```

**提示：**
- 每次重啟 Cloudflare Tunnel 後，URL 可能改變，需要重新設定
- 使用永久 Tunnel 可以避免這個問題（參考進階設定）

---

## 進階設定

### 修改 AI 回應行為

編輯 `.env` 文件：

```bash
# 修改模型（只改這一行，其他設定自動適用）
OLLAMA_MODEL=qwen3.5:35b-a3b  # 高品質（慢）or qwen3.5:9b（快速）

# 修改 Ollama API 端點
OLLAMA_BASE_URL=http://ollama:11434

# 修改日誌級別（DEBUG, INFO, WARNING, ERROR）
LOG_LEVEL=INFO

# 修改速率限制
RATE_LIMIT_MAX_REQUESTS=30      # 每分鐘最大請求數
RATE_LIMIT_WINDOW_SECONDS=60    # 時間窗口（秒）

# 修改佇列設定
QUEUE_MAX_SIZE=10               # 最大佇列大小
QUEUE_TIMEOUT_SECONDS=480       # 完整流程：classify(30) + search(20) + think(300) + sleep(2) + retry(90) = 442s < 480s
```

修改後重啟服務：
```bash
docker compose restart linebot
```

### 設定 Google Drive 同步

**用途：**
- 自動同步系統提示詞（`system_prompt.md`）
- 自動同步圖片映射（`image_map.json`）
- 使用 `!img` 指令發送預設圖片
- 使用 `!reload` 指令重新載入設定

**步驟：**

1. **建立 Google Cloud 專案並啟用 Drive API**
2. **建立服務帳戶並下載金鑰**
3. **在 Google Drive 建立資料夾並分享給服務帳戶**
4. **設定 `.env`**：
   ```bash
   GOOGLE_SERVICE_ACCOUNT_FILE=/path/to/service_account.json
   DRIVE_FOLDER_ID=your_folder_id
   DRIVE_SYNC_INTERVAL_SECONDS=45
   ```

詳細步驟請參考：`docs/setup-guide-zh-TW.md`

### 使用永久 Cloudflare Tunnel

**設定自己的域名：**

```bash
# 1. 登入 Cloudflare
cloudflared tunnel login

# 2. 建立 Tunnel
cloudflared tunnel create linebot

# 3. 設定 DNS
cloudflared tunnel route dns linebot bot.yourdomain.com

# 4. 建立設定檔
nano ~/.cloudflared/config.yml
```

`config.yml` 內容：
```yaml
tunnel: <tunnel-id>
credentials-file: /root/.cloudflared/<tunnel-id>.json

ingress:
  - hostname: bot.yourdomain.com
    service: http://linebot:8000
  - service: http_status:404
```

**修改 docker compose.yml**：
```yaml
cloudflared:
  image: cloudflare/cloudflared:latest
  container_name: cloudflared
  restart: unless-stopped
  command: tunnel run linebot
  volumes:
    - ~/.cloudflared:/etc/cloudflared
```

詳細步驟請參考：`docs/setup-guide-zh-TW.md`

### 設定管理員通知

在 `.env` 中設定：

```bash
# 管理員 LINE User ID（逗號分隔）
ADMIN_USER_IDS=U1234567890abcdef1234567890abcdef

# 最低通知級別（critical, warning, info）
ADMIN_ALERT_LEVEL=warning
```

---

## 專案結構

```
AI-linebot/
 src/                        # 原始碼
    models/                # 資料模型
       llm_request.py     # LLM 請求模型
       prompt_config.py   # 提示詞配置
       image_mapping.py   # 圖片映射
       ...
    services/              # 服務層
       line_service.py    # LINE API 整合
       ollama_service.py  # Ollama 整合
       queue_service.py   # 佇列管理
       ...
    handlers/              # 指令處理器
       hej_handler.py     # !hej 指令
       img_handler.py     # !img 指令
       ...
    utils/                 # 工具函數
    config.py              # 配置管理
 main.py                    # 主程式
 docker-compose.yml         # Docker 配置
 Dockerfile                 # Docker 映像
 .env                       # 環境變數
 requirements.txt           # Python 依賴
 start.sh                   # 啟動腳本
 get-url.sh                 # 獲取 URL 腳本
 START.md                   # 本文件
```

---

## 系統需求

- **作業系統**：Linux / macOS / Windows with WSL2
- **Docker**：20.10+
- **Docker Compose**：2.0+
- **GPU**（可選但推薦）：NVIDIA GPU with CUDA support
- **硬碟空間**：至少 5GB（用於模型）
- **記憶體**：至少 4GB RAM

---

## 當前配置

 **已配置**：
- LINE Channel Secret
- LINE Channel Access Token
- Ollama 模型（qwen3.5:35b-a3b 高品質 或 qwen3.5:9b 快速）
- GPU 支援（RTX 4080）
- Cloudflare Tunnel（臨時 URL）

 **可選配置**：
- Google Drive 同步
- 管理員通知
- 永久 Cloudflare Tunnel

---

## 更多資源

- **專案 README**：[README.md](README.md)
- **line 訊息用量**：https://manager.line.biz/account/@033jhxzy/purchase
- **tavily 搜尋用量**：https://app.tavily.com/home




---

**需要協助？** 查看日誌或參考上方的常見問題。
