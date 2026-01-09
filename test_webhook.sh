#!/bin/bash

# 測試 Webhook 端點

# 顏色設定
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "========================================="
echo "測試 LINE Bot Webhook"
echo "========================================="
echo ""

# 檢查服務是否運行
echo -e "${YELLOW}1. 檢查服務狀態...${NC}"
if ! docker-compose ps | grep -q "Up"; then
    echo -e "${RED}❌ 服務未運行！請先執行 ./start.sh${NC}"
    exit 1
fi
echo -e "${GREEN}✅ 服務正在運行${NC}"
echo ""

# 測試健康檢查端點
echo -e "${YELLOW}2. 測試健康檢查端點...${NC}"
HEALTH_RESPONSE=$(curl -s http://localhost:8000/health)
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ 健康檢查端點正常${NC}"
    echo "$HEALTH_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$HEALTH_RESPONSE"
else
    echo -e "${RED}❌ 健康檢查端點失敗${NC}"
fi
echo ""

# 測試根端點
echo -e "${YELLOW}3. 測試根端點...${NC}"
ROOT_RESPONSE=$(curl -s http://localhost:8000/)
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ 根端點正常${NC}"
    echo "$ROOT_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$ROOT_RESPONSE"
else
    echo -e "${RED}❌ 根端點失敗${NC}"
fi
echo ""

# 檢查 Ollama 連接
echo -e "${YELLOW}4. 檢查 Ollama 服務...${NC}"
OLLAMA_MODELS=$(docker-compose exec -T ollama ollama list 2>/dev/null)
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Ollama 服務正常${NC}"
    echo "$OLLAMA_MODELS"
else
    echo -e "${RED}❌ Ollama 服務異常${NC}"
fi
echo ""

# 獲取 Cloudflare URL
echo -e "${YELLOW}5. 獲取 Cloudflare Tunnel URL...${NC}"
CF_URL=$(docker logs cloudflared 2>&1 | grep -o 'https://[a-zA-Z0-9-]*\.trycloudflare\.com' | head -1)
if [ -n "$CF_URL" ]; then
    echo -e "${GREEN}✅ Cloudflare Tunnel URL:${NC}"
    echo "   $CF_URL"
    echo ""
    echo -e "${YELLOW}   測試公開訪問...${NC}"
    PUBLIC_RESPONSE=$(curl -s "$CF_URL/health" --max-time 5)
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}   ✅ 公開訪問正常${NC}"
    else
        echo -e "${RED}   ❌ 公開訪問失敗${NC}"
    fi
else
    echo -e "${RED}❌ 無法獲取 Cloudflare Tunnel URL${NC}"
fi
echo ""

# 查看最近的日誌
echo -e "${YELLOW}6. 最近的 LINE Bot 日誌:${NC}"
docker-compose logs --tail=10 linebot
echo ""

echo "========================================="
echo "測試完成！"
echo "========================================="
echo ""
echo -e "${YELLOW}下一步:${NC}"
echo "1. 將 Cloudflare URL 設定到 LINE Developers Console"
echo "2. 在 LINE 中發送: !hej 你好"
echo "3. 查看即時日誌: docker-compose logs -f linebot"
