import os
import sys
import json
import subprocess
import time
import urllib.request
import webbrowser

# ==========================================
# 🚀 A-Daily-Quant 一键启动与初始化向导
# ==========================================

CONFIG_FILE = "config.json"


def check_python_version():
    """检查 Python 版本"""
    print("🔍 [1/5] 检查运行环境...")
    if sys.version_info < (3, 9):
        print("❌ 错误: 本项目需要 Python 3.9 或更高版本。")
        sys.exit(1)
    print(f"✅ Python 版本检查通过: {sys.version.split()[0]}")


def install_requirements():
    """静默检查并安装依赖"""
    print("📦 [2/5] 检查核心依赖...")
    try:
        import pandas
        import fastapi
        import uvicorn
        import tushare

        print("✅ 依赖库已就绪")
    except ImportError:
        print("⏳ 第一次运行，正在自动安装所需依赖库，这可能需要一点时间...")
        try:
            subprocess.check_call(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "-r",
                    "requirements.txt",
                    "--quiet",
                ]
            )
            print("✅ 依赖库安装完成")
        except Exception as e:
            print(
                f"❌ 依赖库安装失败，请手动运行 'pip install -r requirements.txt'。错误: {e}"
            )
            sys.exit(1)


def setup_config():
    """向导式生成 config.json"""
    print("⚙️  [3/5] 检查配置文件...")
    if os.path.exists(CONFIG_FILE):
        print("✅ 配置文件已存在")
        return

    print("==================================================")
    print("🎉 欢迎使用 A-Daily-Quant (A股每日量化与Agent分析)")
    print("初始化向导将帮助您快速生成配置文件，所有输入后续均可在 config.json 中修改")
    print("==================================================")

    # 交互式问答
    tushare_token = input(
        "1. 请输入您的 Tushare Token (用于获取股票数据) [按回车跳过则使用默认]: "
    ).strip()
    if not tushare_token:
        tushare_token = "your-tushare-token"

    print("\n2. 请配置您的大模型 (LLM) 服务:")
    print("   [1] 兼容 OpenAI 格式 (例如 Deepseek, Kimi, 各种闭源API代理等) - 强烈推荐")
    print("   [2] 智谱 GLM API")
    print("   [3] 默认跳过 (稍后手动配置)")

    llm_choice = input("👉 请选择大模型对接方式 [1/2/3]: ").strip()

    api_provider = "gemini-openai"
    api_key = ""
    base_url = ""
    model = "gemini-1.5-pro"

    if llm_choice == "1":
        api_provider = "gemini-openai"
        base_url = input(
            "  🌐 API Base URL (例如 https://api.deepseek.com/v1): "
        ).strip()
        api_key = input("  🔑 API Key: ").strip()
        model = input("  🤖 模型名称 (例如 deepseek-chat): ").strip()
    elif llm_choice == "2":
        api_provider = "glm"
        api_key = input("  🔑 智谱 API Key: ").strip()
        model = "glm-4"

    # 生成基础配置
    config_data = {
        "data_source": {"provider": "tushare", "tushare_token": tushare_token},
        "database": {"type": "sqlite", "db_file": "a_daily_quant.db"},
        "api": {"provider": api_provider},
        f"api_{api_provider}": {
            "provider": api_provider,
            "api_key": api_key,
            "base_url": base_url,
            "model": model,
        },
        "analysis": {"lookback_days": 365, "ma_short": 20, "ma_long": 60},
        "selection_rules": {
            "enabled": True,
            "min_score": 70,
            "max_final_candidates": 5,
        },
    }

    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config_data, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 配置文件已生成: {CONFIG_FILE}\n")


def init_database_and_prompts():
    """初始化数据库并注入预设的 Agent Prompts"""
    print("💾 [4/5] 检查并初始化本地数据库...")
    # 通过设置环境变量强制使用 SQLite
    os.environ["DB_TYPE"] = "sqlite"

    try:
        import database

        # 导入时 database.py 会自动建表
        print("✅ 数据库架构就绪 (SQLite)")

        # 执行内建脚本灌入预设的 Agent Prompts
        if os.path.exists("add_agent_prompts.py"):
            subprocess.run(
                [sys.executable, "add_agent_prompts.py"], capture_output=True
            )
            print("✅ 预设策略与 Agent 模板已就绪")

    except Exception as e:
        print(f"⚠️ 数据库初始化或脚本执行遇到小问题，可能会影响部分功能: {e}")


def start_server():
    """拉起后端服务并打开浏览器"""
    print("🚀 [5/5] 正在启动后台服务，请不要关闭终端...")
    os.environ["DB_TYPE"] = "sqlite"

    port = 8100
    url = f"http://127.0.0.1:{port}"

    try:
        # 使用 subprocess 拉起 web_server
        server_process = subprocess.Popen([sys.executable, "web_server.py"])

        # 轮询等待服务可用
        max_retries = 30
        for _ in range(max_retries):
            try:
                urllib.request.urlopen(f"{url}/api/config")
                print(f"\n🎉 启动成功！控制面板运行于: {url}")
                webbrowser.open(url)
                break
            except Exception:
                time.sleep(0.5)
        else:
            print(
                f"\n⚠️ 服务似乎启动较慢，如果控制面板无法访问，请检查日志。地址: {url}"
            )

        # 保持运行直到被杀死
        server_process.wait()

    except KeyboardInterrupt:
        print("\n🛑 服务已安全关闭。")
        server_process.terminate()


if __name__ == "__main__":
    check_python_version()
    install_requirements()
    setup_config()
    init_database_and_prompts()
    start_server()
