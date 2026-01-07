#!/bin/bash
# A股交易纪律助手启动脚本

echo "🚀 启动 A股交易纪律助手..."
echo ""

# 激活虚拟环境
source .venv/bin/activate

# 运行主程序
python main.py

# 提示查看报告
echo ""
echo "✅ 分析完成！请查看生成的报告文件：daily_strategy_*.md"
