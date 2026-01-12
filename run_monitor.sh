#!/bin/bash
# 盘中实时监控启动脚本

echo "🚀 启动 A股实时监控助手 (Web)..."
echo "🌐 访问地址: http://127.0.0.1:8100"
echo ""

# 激活虚拟环境
source .venv/bin/activate

# 运行 Web 服务
# 使用 --reload 方便调试，生产环境可去掉
uvicorn web_server:app --reload --host 0.0.0.0 --port 8100