#!/bin/bash

# Configuration
PORT=8100
HOST="127.0.0.1"
URL="http://$HOST:$PORT"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 正在启动 A股策略监控面板...${NC}"

# 1. Check Python Environment
if [ -d ".venv" ]; then
    source .venv/bin/activate
else
    echo -e "${RED}❌ 未找到虚拟环境 (.venv)，请先运行安装步骤。${NC}"
    exit 1
fi

# 2. Check Port
if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null ; then
    echo -e "${RED}⚠️  端口 $PORT 已被占用。正在尝试关闭旧进程...${NC}"
    kill $(lsof -Pi :$PORT -sTCP:LISTEN -t)
    sleep 1
fi

# 3. Start Server in Background
echo -e "正在启动 Web 服务..."
# Using exec to run python directly or via uvicorn
# We run web_server.py which invokes uvicorn internally
python web_server.py > /tmp/ashare_monitor.log 2>&1 &
SERVER_PID=$!

# 4. Wait for Server to be Ready
echo -n "等待服务就绪"
MAX_RETRIES=30
count=0
while ! curl -s $URL > /dev/null; do
    echo -n "."
    sleep 0.5
    count=$((count+1))
    if [ $count -ge $MAX_RETRIES ]; then
        echo -e "\n${RED}❌ 服务启动超时！请检查日志 /tmp/ashare_monitor.log${NC}"
        kill $SERVER_PID
        exit 1
    fi
done
echo -e "\n${GREEN}✅ 服务已启动！${NC}"

# 5. Open Browser
if [[ "$OSTYPE" == "darwin"* ]]; then
    open $URL
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    xdg-open $URL
elif [[ "$OSTYPE" == "msys" ]]; then
    start $URL
fi

echo -e "${BLUE}🌐 面板已在浏览器中打开: $URL${NC}"
echo -e "${BLUE}⌨️  按 Ctrl+C 停止服务${NC}"

# 6. Trap Cleanup
cleanup() {
    echo -e "\n${BLUE}🛑 正在关闭服务...${NC}"
    kill $SERVER_PID
    exit 0
}
trap cleanup SIGINT

# Keep script running to maintain the trap
wait $SERVER_PID