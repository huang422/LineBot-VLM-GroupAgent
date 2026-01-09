#!/bin/bash

# LINE Bot with Ollama - 啟動腳本

echo "========================================="
echo "LINE Bot with Ollama VLM - 啟動中..."
echo "========================================="
echo ""

# 檢查 .env 檔案是否存在
if [ ! -f .env ]; then
    echo "❌ 錯誤：找不到 .env 檔案"
    echo "請先複製 .env.example 到 .env 並填入必要的設定"
    exit 1
fi

# 啟動 Docker Compose
echo "正在啟動服務..."
docker-compose up -d

# 等待服務啟動
echo ""
echo "等待服務啟動..."
sleep 5

# 檢查服務狀態
echo ""
echo "========================================="
echo "服務狀態："
echo "========================================="
docker-compose ps

# 獲取 Cloudflare Tunnel URL
echo ""
echo "========================================="
echo "正在獲取 Cloudflare Tunnel URL..."
echo "========================================="
sleep 3
docker logs cloudflared 2>&1 | grep -o 'https://[a-zA-Z0-9-]*\.trycloudflare\.com' | head -1

echo ""
echo "========================================="
echo "啟動完成！"
echo "========================================="
echo ""
echo "查看即時日誌："
echo "  docker-compose logs -f"
echo ""
echo "查看 Cloudflare URL："
echo "  ./get-url.sh"
echo ""
echo "停止服務："
echo "  docker-compose down"
echo ""
