#!/bin/bash
# 盘中实时监控启动脚本 - 统一启动前后端

echo "🚀 启动 A股实时监控助手..."
echo ""

# 激活虚拟环境
source .venv/bin/activate

# 强制构建前端
echo "📦 正在重新构建 Vue 前端..."
cd frontend
npm install
npm run build
cd ..
echo "✅ 前端构建完成"

echo ""
echo "🌐 访问地址: http://127.0.0.1:8100"
echo "💡 提示: 后端将自动服务前端静态文件"
echo ""
echo "🎯 启动 Web 服务..."
echo "   按 Ctrl+C 停止服务"
echo ""

# 运行 Web 服务
# 使用 --reload 方便调试，生产环境可去掉
uvicorn web_server:app --reload --host 0.0.0.0 --port 8100