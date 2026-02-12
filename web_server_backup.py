"""
Web Server for A-Share Strategy Monitor
A股策略监控系统 Web 服务器
为前端提供 API 并运行后台监控任务。
"""
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn
import logging
import asyncio
from datetime import datetime
import markdown
import os
import subprocess
import re
import sys
import json
import pandas as pd
from collections import deque
from pathlib import Path
from typing import Optional

# 清除代理环境以防止与 akshare 的连接问题
for env_var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']:
    if env_var in os.environ:
        print(f"⚠️ Clearing proxy environment variable: {env_var}")
        os.environ.pop(env_var)

# 强制设置 no_proxy 以忽略任何系统级代理
os.environ['no_proxy'] = '*'

from monitor_engine import MonitorEngine
from data_fetcher import fetch_data_dispatcher, calculate_start_date, fetch_stock_info, fetch_money_flow, fetch_dragon_tiger_data, load_sector_map, get_sector_performance
from indicator_calc import calculate_indicators, get_latest_metrics # 评分 API 需要导入
from monitor_engine import get_realtime_data # 评分 API 需要导入
from etf_score import apply_etf_score # ETF 评分需要导入
from data_provider.base import DataFetcherManager # 新的数据管理器
import database  # 添加数据库导入
from stock_screener import print_detailed_metrics # 导入日志辅助函数
from data_fetcher_ts import fetch_stock_data_ts, fetch_daily_basic_ts
from data_fetcher_tx import get_stock_realtime_tx
from stock_scoring import get_score

app = FastAPI(title="A-Share Strategy Monitor")

# 初始化引擎
monitor_engine = MonitorEngine()
# 初始化数据管理器
data_manager = DataFetcherManager()

# 设置模板
templates = Jinja2Templates(directory="templates")

# 配置日志（抑制 Uvicorn 访问日志）
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("uvicorn.error").setLevel(logging.WARNING)

# 全局状态
market_state = {
    "index": {"name": "初始化中...", "price": 0, "change_pct": 0},
    "stocks": [],
    "last_update": "N/A",
    "is_monitoring": False, # 监控开关 - 默认关闭，由用户手动开启
    "config": {
        "update_interval": 10  # 默认
    }
}

async def market_data_loop():
    """无限循环更新数据"""
    print("🚀 后台监控任务已启动 (默认暂停，等待用户开启).")
    while True:
        try:
            # 检查开关
            if not market_state["is_monitoring"]:
                market_state["last_update"] = "监控已暂停 - 点击按钮开启"
                await asyncio.sleep(2)
                continue

            # 刷新配置
            config = monitor_engine.load_config() # 热重载配置
            interval = config.get('monitor', {}).get('update_interval_seconds', 10)
            market_state["config"]["update_interval"] = interval
            
            # 1. 更新指数
            # 检查 monitor_engine 是否有该方法，否则添加它
            if hasattr(monitor_engine, 'load_config') is False:
                # 为了健壮性进行热补丁，以防文件顺序更改，
                # 但在本地 monitor_engine.load_config 作为全局函数存在
                # 我们需要调用模块级函数或将其设为静态
                from monitor_engine import load_config as _load_config
                monitor_engine.load_config = lambda: _load_config()
        
            index_data = monitor_engine.get_market_index()
            market_state["index"] = index_data
            
            # 2. 更新股票
            stocks_data = monitor_engine.run_check()
            market_state["stocks"] = stocks_data
            
            market_state["last_update"] = datetime.now().strftime("%H:%M:%S")
            print(f"🔄 市场数据已于 {market_state['last_update']} 更新 (下次更新在 {interval}秒后)")
            
            await asyncio.sleep(interval)
            
        except Exception as e:
            print(f"❌ 后台循环出错: {e}")
            await asyncio.sleep(10) # Retry delay

@app.on_event("startup")
async def startup_event():
    """启动时运行初始检查"""
    monitor_engine.refresh_targets()
    # 启动后台循环 (默认暂停状态)
    asyncio.create_task(market_data_loop())
    print("📋 监控系统已就绪，等待用户手动开启...")

# 检查是否使用 Vue 前端 (构建后的静态文件)
VUE_FRONTEND_PATH = Path(__file__).parent / "frontend" / "dist"
USE_VUE_FRONTEND = VUE_FRONTEND_PATH.exists() and (VUE_FRONTEND_PATH / "index.html").exists()

@app.get("/api/status")
async def get_status():
    """前端轮询调用的 API"""
    # 如果监控未激活且股票列表为空，则从数据库加载
    if not market_state["is_monitoring"] and not market_state.get("stocks"):
        monitor_engine.refresh_targets()
        # 从数据库持仓中获取静态股票信息
        holdings = database.get_all_holdings()
        if holdings:
            market_state["stocks"] = [
                {
                    "symbol": h["symbol"],
                    "name": h["name"],
                    "price": 0,
                    "change_pct": 0,
                    "type": "holding",
                    "asset_type": h.get("asset_type", "stock"),
                    "cost_price": h.get("cost_price", 0),
                    "position_size": h.get("position_size", 0),
                    "volume_ratio": 0,
                    "status": "等待监控开启"
                }
                for h in holdings
            ]
    # 立即返回缓存状态（非阻塞）
    return market_state

class HoldingBase(BaseModel):
    symbol: str
    name: str = ""
    asset_type: str = "stock"
    cost_price: float = 0.0
    position_size: int = 0

class HoldingUpdate(BaseModel):
    cost_price: Optional[float] = None
    position_size: Optional[int] = None

@app.get("/api/stock/search/{symbol}")
async def search_stock(symbol: str):
    """按代码搜索股票信息"""
    if not symbol or len(symbol) < 3:
        return {"status": "error", "message": "Invalid symbol"}
    
    try:
        stock_info = fetch_stock_info(symbol)
        if stock_info:
            return {
                "status": "success",
                "data": stock_info
            }
        else:
            return {
                "status": "not_found",
                "message": f"未找到股票 {symbol} 的信息"
            }
    except Exception as e:
        print(f"❌ Error searching stock {symbol}: {e}")
        return {
            "status": "error",
            "message": f"搜索失败: {str(e)}"
        }

@app.get("/api/holdings")
async def get_holdings():
    """从数据库获取所有持仓及最新分析"""
    today = datetime.now().strftime('%Y-%m-%d')
    holdings = database.get_all_holdings(analysis_date=today)
    # 如果需要，用最新分析进行充实，或由前端进行关联
    return holdings

def refresh_market_state_from_db():
    """立即将 market_state['stocks'] 与数据库持仓同步的辅助函数"""
    try:
        holdings = database.get_all_holdings()
        if not holdings:
            market_state["stocks"] = []
            return

        # 尽可能将当前价格映射到新列表以避免闪烁 0
        current_prices = {s['symbol']: s for s in market_state.get('stocks', [])}
        
        new_stocks_list = []
        for h in holdings:
            existing = current_prices.get(h['symbol'])
            if existing:
                # 更新元数据但保留价格/状态
                existing['name'] = h['name']
                existing['cost_price'] = h.get('cost_price', 0)
                existing['position_size'] = h.get('position_size', 0)
                existing['asset_type'] = h.get('asset_type', 'stock')
                new_stocks_list.append(existing)
            else:
                # 新股票
                new_stocks_list.append({
                    "symbol": h["symbol"],
                    "name": h["name"],
                    "price": 0,
                    "change_pct": 0,
                    "type": "holding",
                    "asset_type": h.get("asset_type", "stock"),
                    "cost_price": h.get("cost_price", 0),
                    "position_size": h.get("position_size", 0),
                    "volume_ratio": 0,
                    "status": "等待监控开启"
                })
        market_state["stocks"] = new_stocks_list
    except Exception as e:
        print(f"Error refreshing market state: {e}")

@app.post("/api/holdings")
async def add_holding(holding: HoldingBase):
    """添加新持仓"""
    # 如果名称为空，尝试获取？暂时让客户端提供或使用默认值
    if not holding.name:
        # 简单回退或让其为空
        holding.name = holding.symbol
        
    success = database.add_holding(
        holding.symbol,
        holding.name,
        holding.cost_price,
        holding.position_size,
        holding.asset_type
    )
    if success:
        monitor_engine.refresh_targets()
        refresh_market_state_from_db()
        return {"status": "success", "message": f"Added {holding.symbol}"}
    else:
        raise HTTPException(status_code=400, detail="Failed to add holding (already exists?)")

@app.put("/api/holdings/{symbol}")
async def update_holding(symbol: str, holding: HoldingUpdate):
    """更新持仓详情"""
    success = database.update_holding(
        symbol,
        cost_price=holding.cost_price,
        position_size=holding.position_size
    )
    if success:
        monitor_engine.refresh_targets()
        refresh_market_state_from_db()
        return {"status": "success", "message": f"Updated {symbol}"}
    else:
        raise HTTPException(status_code=400, detail="Failed to update holding")

@app.delete("/api/holdings/{symbol}")
async def delete_holding(symbol: str):
    """移除持仓"""
    success = database.remove_holding(symbol)
    if success:
        monitor_engine.refresh_targets()
        refresh_market_state_from_db()
        return {"status": "success", "message": f"Removed {symbol}"}
    else:
        raise HTTPException(status_code=404, detail="Holding not found")

@app.get("/api/selections")
async def get_selections(date: str = None):
    """从数据库获取每日精选"""
    print(f"📡 API /api/selections called with date='{date}' (Type: {type(date)})")
    
    # 如果未提供日期，数据库层处理最新数据的检索
    selections = database.get_daily_selections(date)
    print(f"📦 Found {len(selections)} selections")

    # 获取可用日期
    try:
        conn = database.get_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT DISTINCT selection_date FROM daily_selections ORDER BY selection_date DESC LIMIT 30")
            dates = [row['selection_date'].strftime('%Y-%m-%d') for row in cursor.fetchall()]
    except Exception as e:
        print(f"❌ Error getting available dates: {e}")
        dates = []

    return {
        "selections": selections,
        "available_dates": dates
    }

@app.post("/api/monitor/toggle")
async def toggle_monitor():
    """切换监控开启/关闭"""
    market_state["is_monitoring"] = not market_state["is_monitoring"]
    status = "running" if market_state["is_monitoring"] else "paused"
    print(f"⏸️ Monitoring switched to: {status}")
    return {"status": status, "is_monitoring": market_state["is_monitoring"]}

@app.post("/api/realtime/refresh")
async def refresh_realtime_data():
    """手动刷新一次实时行情数据（不依赖监控开关）"""
    try:
        print("📡 收到前端请求 - 刷新实时行情数据...")

        # 1. 更新指数数据
        index_data = monitor_engine.get_market_index()
        market_state["index"] = index_data

        # 2. 更新股票实时数据
        stocks_data = monitor_engine.run_check()
        market_state["stocks"] = stocks_data

        # 3. 更新时间戳
        market_state["last_update"] = datetime.now().strftime("%H:%M:%S")

        print(f"✅ 实时数据刷新完成: {len(stocks_data)} 只股票, 指数: {index_data['name']} {index_data['price']}")

        return {
            "status": "success",
            "stocks": stocks_data,
            "index": index_data,
            "last_update": market_state["last_update"],
            "message": f"成功获取 {len(stocks_data)} 只股票实时数据"
        }
    except Exception as e:
        print(f"❌ 实时数据刷新失败: {e}")
        return {
            "status": "error",
            "message": f"数据获取失败: {str(e)}",
            "stocks": [],
            "index": market_state["index"]
        }



@app.get("/api/kline/{symbol}")
async def get_kline_data(symbol: str, period: str = 'daily'):
    """
    获取图表的 K 线数据
    周期：日线、周线、月线 (daily, weekly, monthly)
    """
    # 1. 查找目标以了解其资产类型
    target = next((t for t in monitor_engine.targets if t['symbol'] == symbol), None)
    
    asset_type = 'stock' # 默认
    if target:
        asset_type = target.get('asset_type', 'stock')
    
    # 2. 将原始 K 线 dataframe 转换为图表的列表格式
    # [Date, Open, Close, Low, High, Volume]
    
    try:
        # 根据周期确定天数
        days_map = {'daily': 365, 'weekly': 365, 'monthly': 730}
        days = days_map.get(period, 365)
        
        start_date = calculate_start_date(days)
        
        # 将周期传递给调度器
        # 使用 DataManager 获取每日股票/ETF 数据以确保稳定性
        if period == 'daily' and asset_type in ['stock', 'etf']:
            try:
                # get_daily_data 返回 (df, source_name)
                df, _ = data_manager.get_daily_data(symbol, start_date=start_date)
            except Exception as e:
                print(f"DataManager Fetch Failed: {e}, falling back to legacy dispatcher")
                df = fetch_data_dispatcher(symbol, asset_type, start_date, period=period)
        else:
            df = fetch_data_dispatcher(symbol, asset_type, start_date, period=period)
        
        if df is None or df.empty:
            return {"status": "error", "message": "No data found"}
            
        # 计算 MA（简单移动平均线）
        # 使用滚动窗口
        df['ma5'] = df['close'].rolling(window=5).mean()
        df['ma10'] = df['close'].rolling(window=10).mean()
        df['ma20'] = df['close'].rolling(window=20).mean()
        df['ma30'] = df['close'].rolling(window=30).mean()
        
        # 将 NaN 填充为 None 以用于图表（ECharts 更好处理 '-' 或 null）
        # 使用对象类型安全地就地替换以允许 None
        df = df.astype(object)
        df = df.where(pd.notnull(df), None)
            
        dates = df['date'].apply(lambda x: x.strftime('%Y-%m-%d') if pd.notnull(x) else '').tolist()
        
        values = []
        volumes = []
        ma5 = []
        ma10 = []
        ma20 = []
        ma30 = []
        
        # Iteration
        for _, row in df.iterrows():
            values.append([
                row['open'],
                row['close'],
                row['low'],
                row['high']
            ])
            volumes.append(row['volume'])
            # 显式检查 None（NaN 已在上文中替换为 None）
            ma5.append(row['ma5'])
            ma10.append(row['ma10'])
            ma20.append(row['ma20'])
            ma30.append(row['ma30'])
            
        return {
            "status": "success",
            "symbol": symbol,
            "name": target['name'] if target else symbol,
            "period": period,
            "dates": dates,
            "values": values,
            "volumes": volumes,
            "ma5": ma5,
            "ma10": ma10,
            "ma20": ma20,
            "ma30": ma30
        }
        
    except Exception as e:
        print(f"Kline Error: {e}")
        return {"status": "error", "message": str(e)}

# --- 报告管理 ---

@app.get("/api/report/latest")
async def get_latest_report():
    """获取最新策略报告的内容（如果可用，则合并部分）"""
    report_dir = "reports"
    if not os.path.exists(report_dir):
        return {"content": "<h3>暂无日报</h3>", "filename": None}

    # 尝试从最新的完整或部分文件中查找日期
    all_files = os.listdir(report_dir)
    # 匹配类似 20250101 的日期
    dates = []
    for f in all_files:
        m = re.search(r"(\d{8})\.md$", f)
        if m:
            dates.append(m.group(1))
    
    if not dates:
        return {"content": "<h3>暂无日报</h3>", "filename": None}
        
    dates.sort(reverse=True)
    latest_date = dates[0]
    
    sections = {
        "market": "",
        "holdings": "",
        "candidates": ""
    }
    
    # 首先尝试读取各个部分
    found_sections = False
    for sec in sections.keys():
        path = os.path.join(report_dir, f"section_{sec}_{latest_date}.md")
        if os.path.exists(path):
            found_sections = True
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    sections[sec] = markdown.markdown(f.read(), extensions=['tables', 'fenced_code'])
            except:
                sections[sec] = "<p>读取失败</p>"
    
    if found_sections:
        return {
            "sections": sections,
            "filename": f"Report_{latest_date}",
            "mode": "sections"
        }

    # 回退到完整旧版文件
    full_path = os.path.join(report_dir, f"daily_strategy_full_{latest_date}.md")
    if os.path.exists(full_path):
        # ... 分割旧版文件的逻辑 ...
         try:
            with open(full_path, 'r', encoding='utf-8') as f:
                md_content = f.read()
                
                parts = {"market": "", "holdings": "", "candidates": ""}
                current_md = md_content
                
                if "# 🎯 今日选股参考" in current_md:
                    pre, candidates = current_md.split("# 🎯 今日选股参考", 1)
                    parts["candidates"] = "# 🎯 今日选股参考" + candidates
                    current_md = pre
                
                if "# 📊 持仓分析日报" in current_md:
                    pre, holdings = current_md.split("# 📊 持仓分析日报", 1)
                    parts["holdings"] = "# 📊 持仓分析日报" + holdings
                    current_md = pre
                    
                parts["market"] = current_md
                
                html_parts = {}
                for k, v in parts.items():
                    html_parts[k] = markdown.markdown(v, extensions=['tables', 'fenced_code']) if v.strip() else ""
                
                return {"sections": html_parts, "filename": f"Full_{latest_date}", "mode": "sections"}
         except:
             pass

    return {"content": "<h3>暂无数据</h3>", "filename": None}

# 报告状态和日志
report_generation_status = {"status": "idle", "message": ""}
report_logs = deque(maxlen=200) # 存储最后 200 行日志

@app.post("/api/report/generate")
async def generate_report(background_tasks: BackgroundTasks, section: str = "all"):
    """触发每日报告生成脚本（可选部分）"""
    if report_generation_status["status"] == "running":
        return JSONResponse(status_code=400, content={"message": "生成任务已在运行中"})
    
    def _run_generation():
        report_generation_status["status"] = "running"
        report_generation_status["message"] = f"正在启动生成 ({section})..."
        report_logs.clear() # 清除旧日志
        
        try:
            # 使用 Popen 作为子进程运行 main.py 以流式传输 stdout
            # 使用 sys.executable 确保我们使用相同的 python 解释器 (venv)
            cmd = [sys.executable, "-u", "main.py", "--section", section]
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            # 逐行读取 stdout
            for line in process.stdout:
                line = line.strip()
                if line:
                    print(f"[Report] {line}") # 也打印到后端控制台
                    report_logs.append(line)
                    # 使用最新日志更新状态消息
                    report_generation_status["message"] = line
            
            process.wait()
            
            if process.returncode == 0:
                report_generation_status["status"] = "success"
                report_generation_status["message"] = "生成成功！请刷新查看。"
                # 如果发现新候选者，刷新目标
                monitor_engine.refresh_targets()
            else:
                report_generation_status["status"] = "error"
                report_generation_status["message"] = f"生成失败 (Code {process.returncode}) - 查看日志详情"
                
        except Exception as e:
             report_generation_status["status"] = "error"
             report_generation_status["message"] = f"执行错误: {str(e)}"
             report_logs.append(f"❌ Exception: {str(e)}")
             
        finally:
             if report_generation_status["status"] == "running":
                 report_generation_status["status"] = "idle"

    background_tasks.add_task(_run_generation)
    return {"status": "started", "message": "策略日报生成任务已启动"}

@app.get("/api/report/status")
async def get_report_status():
    return report_generation_status

@app.get("/api/report/logs")
async def get_report_logs():
    return {"logs": list(report_logs)}

# --- 单只股票分析 ---

single_analysis_status = {}  # {symbol: {"status": "idle"|"running"|"success"|"error", "message": "", "result": ""}}
realtime_analysis_status = {} # {symbol: {"status": "idle"|"running"|"success"|"error", "message": "", "result": ""}}


@app.post("/api/analyze/{symbol}/score")
async def calculate_stock_score(symbol: str):
    """
    阶段 1：仅计算指标和评分（无 AI 分析）。
    保存到 'daily_metrics' 表。
    数据源：Tushare Unified (stock_scoring.py)
    """
    print("🚀🚀🚀 /score calculate_stock_score (Unified Tushare Source)", symbol)
    try:
        # 1. 获取信息 (为了 Cost Price)
        holdings = database.get_all_holdings()
        stock_info = next((h for h in holdings if h['symbol'] == symbol), None)
        cost_price = float(stock_info.get('cost_price') or 0) if stock_info else 0.0
        
        # 自动检测类型 (如果不在持仓中，get_score 内部也有简单判断，但这里传递更好)
        # 如果 stock_info 存在，使用它的 asset_type，否则为 stock
        asset_type = stock_info.get('asset_type', 'stock') if stock_info else 'stock'

        # 2. 调用统一评分模块
        latest = get_score(symbol, cost_price=cost_price, asset_type=asset_type, include_news=True)
        
        if not latest:
             return JSONResponse(status_code=500, content={"message": "评分计算失败（数据获取失败）"})

        print(f"\n   --- DETAILED ANALYSIS: {latest.get('name', 'Unknown')} ({latest.get('symbol', '')}) ---")
        print(f"   {latest}")

        # 3. 后处理：保存到 daily_metrics
        today = datetime.now().strftime('%Y-%m-%d')

        # 处理模式列表为字符串
        pattern_list = latest.get('pattern_details', [])
        latest['pattern_flags'] = ",".join(pattern_list) if pattern_list else ""
        
        success = database.save_daily_metrics(today, latest)
        
        if success:
            return {
                "status": "success",
                "message": "指标计算完成，已存入数据库",
                "data": latest
            }
        else:
             return JSONResponse(status_code=500, content={"message": "数据库保存失败"})
             
    except Exception as e:
        print(f"Calculate Score Error: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"message": f"计算失败: {str(e)}"})

@app.get("/api/analyze/{symbol}/metrics")
async def get_stock_metrics(symbol: str, date: str = None):
    """从数据库获取计算的指标评分"""
    if not date:
        date = datetime.now().strftime('%Y-%m-%d')
    
    metrics = database.get_daily_metrics(symbol, date)
    if metrics:
        return {
            "status": "success",
            "data": metrics
        }
    else:
        # 如果今天未找到，尝试获取昨天的？或者直接返回未找到
        # 为了更好的用户体验，也许检查是否有最近的指标？
        # 但如果我们要显示当前状态，我们特别需要“今天的指标”。
        return {
            "status": "not_found",
            "message": "No metrics found for this date"
        }

@app.get("/api/analyze/{symbol}/report/stream")
async def analyze_stock_report_stream(symbol: str, mode: str = "multi_agent"):
    """
    流式传输 AI 分析报告 (SSE)。
    模式：
    - multi_agent：全面辩论（技术派 vs 风险派 vs 基本面派 -> CIO）
    - single_prompt：使用单一稳健提示进行快速分析（旧版/快速）
    """
    async def _stream_generator():
        try:
            # 1. 准备数据
            from data_fetcher import fetch_data_dispatcher, calculate_start_date, fetch_stock_info
            from indicator_calc import calculate_indicators, get_latest_metrics
            from monitor_engine import get_realtime_data
            
            yield f"data: {json.dumps({'type': 'progress', 'value': 5, 'message': '🔍 检查本地指标缓存...'})}\n\n"
            
            # 检查数据库中是否有今天的指标
            today = datetime.now().strftime('%Y-%m-%d')
            db_metrics = database.get_daily_metrics(symbol, today)
            
            # 获取信息
            holdings = database.get_all_holdings()
            stock_info = next((h for h in holdings if h['symbol'] == symbol), None)
            if not stock_info:
                stock_info = fetch_stock_info(symbol)
                if stock_info:
                    stock_info['symbol'] = symbol
            
            if not stock_info:
                yield f"data: {json.dumps({'type': 'error', 'content': '找不到标的信息'})}\n\n"
                return

            tech_data = {}  # 技术指标
            rt_data = {}    # 行情数据
            index_data = {} # Initialize default

            # 策略：如果数据库中存在指标，则使用它们（快速路径）。否则获取（慢速路径）。
            if db_metrics:
                 yield f"data: {json.dumps({'type': 'step', 'content': '✅ 命中本地指标缓存，跳过重复计算'})}\n\n"
                 yield f"data: {json.dumps({'type': 'progress', 'value': 20, 'message': '🚀 加载缓存数据...'})}\n\n"
                 
                 # 从 db_metrics 重构 tech_data
                 tech_data = db_metrics
                 tech_data['close'] = float(db_metrics['price'] or 0)
                 tech_data['ma20'] = float(db_metrics['ma20'] or 0)
                 tech_data['composite_score'] = db_metrics.get('composite_score', 0)
                 tech_data['score_breakdown'] = db_metrics.get('score_breakdown', [])
                 
                 # 我们仍然需要实时指数数据作为上下文
                 monitor_engine_conf = monitor_engine.load_config()
                 index_data = monitor_engine.get_market_index()
                 
                 # 从指标 + 指数构建最小 rt_data
                 rt_data = {
                     'price': float(db_metrics['price']),
                     'change_pct': float(db_metrics['change_pct']),
                     'volume_ratio': float(db_metrics['volume_ratio'])
                 }
                 
                 # [Patch] 尝试获取官方收盘数据以修正价格 (解决盘中缓存导致盘后价格不一致问题)
                 yield f"data: {json.dumps({'type': 'progress', 'value': 22, 'message': '🔍 校验官方收盘数据...'})}\n\n"
                 from data_fetcher_ts import fetch_latest_daily_ts, fetch_daily_basic_ts
                 
                 # Tushare returns YYYYMMDD, db uses YYYY-MM-DD
                 today_str = today.replace('-', '')
                 official_daily = fetch_latest_daily_ts(symbol)
                 
                 if official_daily:
                     print(f"✅ Found official daily close for {symbol}: {official_daily['close']} (Date: {official_daily['date']})")
                     # 无论日期是否完全匹配今天（可能是周五收盘周一做复盘），优先使用 Daily 接口的准确收盘价
                     rt_data['price'] = official_daily['close']
                     rt_data['change_pct'] = official_daily['pct_chg']
                     tech_data['close'] = official_daily['close']
                     tech_data['change_pct'] = official_daily['pct_chg'] # strict update
                     
                     # Sync Date for Basic Data (Ensure we fetch turnover for the SAME day)
                     target_date_str = official_daily['date']
                 else:
                     target_date_str = today_str
                 
                 # Refresh basic data (turnover/VR)
                 basic_data = fetch_daily_basic_ts(symbol, target_date_str)
                 if basic_data:
                     if basic_data.get('volume_ratio'):
                         rt_data['volume_ratio'] = basic_data['volume_ratio']
                         tech_data['volume_ratio'] = basic_data['volume_ratio']
                     if basic_data.get('turnover_rate'):
                         tech_data['turnover_rate'] = basic_data['turnover_rate']
                 
            else:
                # --- 慢速路径（获取并计算） ---
                yield f"data: {json.dumps({'type': 'progress', 'value': 10, 'message': '📉 正在下载历史K线数据(120天)...'})}\n\n"
                
                # 获取历史 (用于计算指标 - 需复权)
                start_date = calculate_start_date()
                asset_type = stock_info.get('asset_type', 'stock')
                
                df = None
                # Use DataManager
                if asset_type in ['stock', 'etf']:
                    try:
                        df, _ = data_manager.get_daily_data(symbol, start_date=start_date)
                    except Exception:
                        pass
                
                if df is None:
                     df = fetch_data_dispatcher(symbol, asset_type, start_date)
                
                if df is None or df.empty:
                    yield f"data: {json.dumps({'type': 'error', 'content': '历史数据获取失败'})}\n\n"
                    return
                
                yield f"data: {json.dumps({'type': 'step', 'content': '✅ 历史数据获取完成'})}\n\n"
                yield f"data: {json.dumps({'type': 'progress', 'value': 15, 'message': '🧮 正在计算技术指标(MA/RSI/MACD)...'})}\n\n"
                df = calculate_indicators(df)
                
                # Tech data from Adjusted History (Correct for MA/MACD)
                tech_data = get_latest_metrics(df, float(stock_info.get('cost_price') or 0))
                
                yield f"data: {json.dumps({'type': 'step', 'content': '✅ 核心指标计算完成'})}\n\n"
                yield f"data: {json.dumps({'type': 'progress', 'value': 25, 'message': ' 正在提取收盘数据(Daily接口)...'})}\n\n"
                
                # 获取指数数据（用于市场上下文）
                monitor_engine_conf = monitor_engine.load_config() # Refresh config
                index_data = monitor_engine.get_market_index()
                
                # --- 重构 rt_data 构建逻辑 (使用 Daily 接口获取精准收盘数据) ---
                from data_fetcher_ts import fetch_latest_daily_ts, fetch_daily_basic_ts
                
                # 1. 尝试获取最新的 DailyRaw 数据 (符合用户预期的不复权收盘价)
                raw_daily = fetch_latest_daily_ts(symbol)
                
                # 2. 获取基础指标 (量比/换手)
                basic_data = fetch_daily_basic_ts(symbol)
                
                if raw_daily:
                    print(f"✅ Using Raw Daily for {symbol}: Close={raw_daily['close']}, Chg={raw_daily['pct_chg']}%")
                    rt_data = {
                        'symbol': symbol,
                        'name': stock_info.get('name', symbol),
                        'price': raw_daily['close'],
                        'change_pct': raw_daily['pct_chg'],
                        'volume_ratio': 0, # Placeholder, fill later
                        'asset_type': asset_type
                    }
                else:
                    # Fallback to DF (Adjusted) if raw daily fails
                    latest_row = df.iloc[-1]
                    prev_row = df.iloc[-2] if len(df) > 1 else latest_row
                    
                    # 优先使用 dataframe 中的 change_pct (如果已恢复)
                    if 'change_pct' in latest_row:
                        change_pct = float(latest_row['change_pct'])
                    else:
                        close_price = float(latest_row['close'])
                        prev_close = float(prev_row['close'])
                        change_pct = ((close_price - prev_close) / prev_close * 100) if prev_close > 0 else 0.0
                        
                    rt_data = {
                        'symbol': symbol,
                        'name': stock_info.get('name', symbol),
                        'price': float(latest_row['close']),
                        'change_pct': round(change_pct, 2),
                        'volume_ratio': float(latest_row.get('volume_ratio', 0)),
                        'asset_type': asset_type
                    }

                # 3. 注入量比和换手 (优先使用 Basic 接口)
                if basic_data:
                    rt_data['volume_ratio'] = basic_data.get('volume_ratio', rt_data.get('volume_ratio', 0))
                    tech_data['turnover_rate'] = basic_data.get('turnover_rate', 0)
                    tech_data['volume_ratio'] = rt_data['volume_ratio']
                else:
                    # Fallback for turnover/VR
                    tech_data['turnover_rate'] = 'N/A'
                    # If VR is 0 in rt_data, try to calculate or keep 0
                
                yield f"data: {json.dumps({'type': 'step', 'content': '✅ 收盘数据提取完成'})}\n\n"
            
            # 通用逻辑：增强的数据获取
            # --- 注入市场上下文 (使用 MonitorEngine 的高级逻辑) ---
            # 1. 基础指数数据
            rt_data['market_index_price'] = index_data.get('price')
            rt_data['market_index_change'] = index_data.get('change_pct')
            
            # 2. 计算高级大盘状态 (Trend + Volume)
            try:
                # 使用 monitor_engine 的缓存获取历史
                if hasattr(monitor_engine, 'get_market_history_cached'):
                    index_df = monitor_engine.get_market_history_cached()
                else:
                    index_df = None
                    
                if index_df is not None and not index_df.empty:
                    # Calculate MA5
                    index_df['ma5'] = index_df['close'].rolling(5).mean()
                    last_row = index_df.iloc[-1]
                    
                    current_price = index_data.get('price') if index_data.get('price', 0) > 0 else last_row['close']
                    ma5_price = last_row['ma5']
                    
                    # Trend
                    trend = "震荡"
                    if current_price > ma5_price * 1.005: trend = "上涨"
                    elif current_price < ma5_price * 0.995: trend = "下跌"
                    
                    # Position
                    pos_desc = "均线上方" if current_price > ma5_price else "均线下方"
                    
                    rt_data['market_status_desc'] = f"{trend} ({pos_desc})"
                else:
                    # Fallback
                    status = "Strong" if index_data.get('change_pct', 0) > 0.5 else ("Weak" if index_data.get('change_pct', 0) < -0.5 else "Neutral")
                    rt_data['market_status_desc'] = f"未知 ({status})"
            except Exception as e:
                print(f"Web Market Status Error: {e}")
                rt_data['market_status_desc'] = "未知"

            # 3. (Optional) Re-inject turnover if needed (already done above)
            # just ensuring variables are consistent
            if 'turnover_rate' not in tech_data:
                 tech_data['turnover_rate'] = 'N/A'
            
            # --- 注入板块信息 ---
            # 单只股票分析可能会错过选股器中使用的板块资金流，所以我们在这里补充它。
            sector_map = load_sector_map()
            sector_name = sector_map.get(symbol, 'N/A')
            
            # 如果不在映射中，也许我们可以获取它或保留为 N/A
            rt_data['sector'] = sector_name
            tech_data['sector'] = sector_name
            
            if sector_name and sector_name != 'N/A':
                 sector_change = get_sector_performance(sector_name)
                 rt_data['sector_change'] = sector_change
                 tech_data['sector_change'] = sector_change
            else:
                 rt_data['sector_change'] = 0
                 tech_data['sector_change'] = 0
                 
            # 要在没有全市场扫描的情况下即时计算排名很难，设为 'N/A'（或在提示中设为 '未知'）
            tech_data['rank_in_sector'] = 'N/A'
            rt_data['rank_in_sector'] = 'N/A'
            
            # 获取资金和龙虎榜（无论快速/慢速路径）
            yield f"data: {json.dumps({'type': 'progress', 'value': 28, 'message': '💸 正在分析资金流向与龙虎榜...'})}\n\n"
            
            # 这些通常足够快，或者也许我们异步获取它们？
            # 为简单起见，这里按顺序执行。
            money_flow = fetch_money_flow(symbol)
            lhb_data = fetch_dragon_tiger_data(symbol)
            
            rt_data['money_flow'] = money_flow
            rt_data['lhb_data'] = lhb_data
            
            yield f"data: {json.dumps({'type': 'step', 'content': '✅ 数据准备就绪，进入AI分析阶段'})}\n\n"

            # API 配置
            provider = monitor_engine_conf.get('api', {}).get('provider', 'openai')
            api_config_key = f"api_{provider}"
            api_config = monitor_engine_conf.get(api_config_key, monitor_engine_conf.get('api'))
            
            if not api_config.get('api_key') and not api_config.get('credentials_path'):
                 yield f"data: {json.dumps({'type': 'error', 'content': 'API Key 未配置'})}\n\n"
                 return

            if mode == 'multi_agent':
                from agent_analyst import MultiAgentSystem
                yield f"data: {json.dumps({'type': 'progress', 'value': 30, 'message': '🧠 正在组建专家辩论团队...'})}\n\n"
                
                system = MultiAgentSystem(api_config)
                
                accumulated_html = ""
                # 传递 start_progress 以从 30% 平滑继续
                async for event_json in system.run_debate_stream(stock_info, tech_data, rt_data, start_progress=35):
                    # 拦截最终结果以保存到数据库？
                    # 流直接生成 json 字符串
                    data = json.loads(event_json)
                    if data['type'] == 'final_html':
                        accumulated_html = data['content']
                        # Save to DB
                        try:
                            # 我们构建一个复合分析对象
                            analysis_data = {
                                'price': rt_data.get('price', 0),
                                'ma20': tech_data.get('ma20', 0),
                                'trend_signal': tech_data.get('ma_arrangement', 'MultiAgent'),
                                'composite_score': tech_data.get('composite_score', 0),
                                'ai_analysis': accumulated_html
                            }
                            # 确保价格有效
                            if analysis_data['price'] == 0 and tech_data.get('close') and tech_data.get('close') > 0:
                                analysis_data['price'] = tech_data['close']
                                
                            today = datetime.now().strftime('%Y-%m-%d')
                            
                            # 检查它是否实际上在持仓中以避免外键错误
                            is_holding = any(h['symbol'] == symbol for h in holdings)
                            
                            if is_holding:
                                # 首先尝试严格保存为持仓分析
                                success = database.save_holding_analysis(symbol, today, analysis_data, mode=mode)
                            else:
                                success = False
                            
                            # 如果不是持仓或保存失败，尝试保存为精选更新
                            if not success:
                                # 我们假设它可能是一个正在被即时分析的候选者
                                # 检查今天是否存在于 daily_selections 中
                                current_selection = database.get_daily_selection(symbol, today)
                                if current_selection:
                                    print(f"⚠️ {symbol} not in holdings, updating daily selection instead.")
                                    # Update selection with new AI analysis
                                    selection_update = {
                                        'symbol': symbol,
                                        'name': current_selection.get('name', ''),
                                        'close_price': analysis_data['price'],
                                        'volume_ratio': current_selection.get('volume_ratio', 0),
                                        'composite_score': analysis_data['composite_score'],
                                        'ai_analysis': accumulated_html # 存储 HTML 还是 Markdown？Agent 返回混合内容（Agents 返回 HTML，CIO 返回 MD）。
                                    }
                                    database.save_daily_selection(today, selection_update)
                                    
                        except Exception as e:
                            print(f"DB Save Error: {e}")
                            
                    yield f"data: {event_json}\n\n"
                    
            else:
                # 回退到单一提示（旧版逻辑移植到流式包装器）
                # 为简单起见，我们只运行阻塞的单次生成并生成结果
                yield f"data: {json.dumps({'type': 'progress', 'value': 40, 'message': '⚡️ 单一专家模型快速分析中...'})}\n\n"
                yield f"data: {json.dumps({'type': 'step', 'content': '⏳ 连接 LLM 模型进行分析...'})}\n\n"
                
                # 我们可以重用现有的 generate_analysis，但它是阻塞的。
                # 理想情况下重写为异步，但现在先包装它。
                from llm_analyst import generate_analysis, format_stock_section
                import markdown
                
                # 为了使其“流式”，我们伪造它或只是等待
                # 实际上 LLM 生成需要时间。
                
                # 在等待时伪造进度提升（因为阻塞）
                # 除非我们使用线程，否则无法在阻塞调用期间真正提升进度，但现在只需等待。
                
                analysis = generate_analysis(
                    stock_info=stock_info,
                    tech_data=tech_data,
                    api_config=api_config,
                    analysis_type="realtime", # 使用实时提示（简化用于快速分析）
                    realtime_data=rt_data
                )
                
                yield f"data: {json.dumps({'type': 'progress', 'value': 90, 'message': '分析生成完毕，正在排版...'})}\n\n"
                
                formatted = format_stock_section(stock_info, tech_data, analysis)
                html = markdown.markdown(formatted, extensions=['tables'])
                
                # Save
                analysis_data = {
                    'price': rt_data.get('price', 0),
                    'ma20': tech_data.get('ma20', 0),
                    'trend_signal': tech_data.get('ma_arrangement', ''),
                    'composite_score': tech_data.get('composite_score', 0),
                    'ai_analysis': formatted
                }
                # Ensure price is valid
                if analysis_data['price'] == 0 and tech_data.get('close') and tech_data.get('close') > 0:
                    analysis_data['price'] = tech_data['close']

                today = datetime.now().strftime('%Y-%m-%d')
                
                # 检查它是否实际上在持仓中以避免外键错误
                is_holding = any(h['symbol'] == symbol for h in holdings)
                
                if is_holding:
                    success = database.save_holding_analysis(symbol, today, analysis_data, mode=mode)
                else:
                    success = False
                
                if not success:
                    # 回退：如果不在持仓中，尝试保存到 daily_selections（候选模式）
                    try:
                        print(f"⚠️ {symbol} not in holdings, attempting to save to daily_selections...")
                        # Try today first
                        current_sel = database.get_daily_selection(symbol, today)
                        target_date = today
                        
                        # If not in today's list, try finding the latest entry (e.g. from yesterday)
                        if not current_sel:
                            current_sel = database.get_daily_selection(symbol, None)
                            if current_sel:
                                target_date = current_sel['selection_date']
                        
                        if current_sel:
                            sel_update = {
                                'symbol': symbol,
                                'name': current_sel.get('name', stock_info.get('name', '')),
                                'close_price': analysis_data['price'],
                                'volume_ratio': current_sel.get('volume_ratio', 0),
                                'composite_score': analysis_data['composite_score'],
                                'ai_analysis': formatted
                            }
                            database.save_daily_selection(target_date, sel_update)
                            print(f"✅ Saved candidate analysis (fallback) for {symbol} on {target_date}")
                        else:
                             print(f"⚠️ {symbol} not found in any daily selections, analysis not saved to DB.")
                    except Exception as save_e:
                        print(f"❌ Failed to save fallback analysis: {save_e}")

                yield f"data: {json.dumps({'type': 'progress', 'value': 100, 'message': '分析完成'})}\n\n"
                yield f"data: {json.dumps({'type': 'result', 'content': formatted})}\n\n"
                yield f"data: {json.dumps({'type': 'final_html', 'content': html})}\n\n"
                yield f"data: {json.dumps({'type': 'complete', 'content': 'Done'})}\n\n"

        except Exception as e:
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'type': 'error', 'content': f'系统错误: {str(e)}'})}\n\n"

    return StreamingResponse(
        _stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )

@app.get("/api/analyze/{symbol}/intraday")
async def analyze_stock_intraday(symbol: str):
    """
    Stream intraday analysis using Tencent Realtime Data + LLM
    盘中实时分析
    """
    async def _stream_generator_intraday():
        try:
             yield f"data: {json.dumps({'type': 'progress', 'value': 5, 'message': '🚀 启动盘中分析...'})}\n\n"
             
             # 0. Import DB function
             from database import save_intraday_log
             
             
             # 1. Fetch Realtime Data (Tencent)
             rt_data = get_stock_realtime_tx(symbol)
             
             if not rt_data:
                 yield f"data: {json.dumps({'type': 'error', 'content': '无法获取腾讯实时数据'})}\n\n"
                 return
                 
             yield f"data: {json.dumps({'type': 'step', 'content': f'✅ 获取实时行情: ￥{rt_data['price']} ({rt_data['change_pct']}%)'})}\n\n"
             yield f"data: {json.dumps({'type': 'progress', 'value': 20, 'message': '📊 获取技术形态上下文...'})}\n\n"

             # 2. Get Context (Metrics)
             today = datetime.now().strftime('%Y-%m-%d')
             
             stock_info = {'symbol': symbol, 'name': rt_data['name'], 'asset_type': 'stock'}
             
             # Context: Use latest metrics from DB or Recalc
             from indicator_calc import calculate_indicators, get_latest_metrics
             from data_fetcher import fetch_data_dispatcher, calculate_start_date
             
             db_metrics = database.get_daily_metrics(symbol, today) 
             if not db_metrics:
                 # Recalc
                 start_date = calculate_start_date()
                 df = fetch_data_dispatcher(symbol, 'stock', start_date)
                 if df is not None and not df.empty:
                     df = calculate_indicators(df)
                     tech_data = get_latest_metrics(df, 0)
                 else:
                     tech_data = {}
             else:
                 tech_data = db_metrics

             yield f"data: {json.dumps({'type': 'progress', 'value': 40, 'message': '🧠 正在进行AI盘中推演...'})}\n\n"

             # 3. Call LLM
             from llm_analyst import generate_analysis
             config = monitor_engine.load_config()
             provider = config.get('api', {}).get('provider', 'openai')
             llm_config = config.get(f'api_{provider}', config.get('llm_api', {}))
             
             # context: Market & Sector
             # 1. Market Index (sh000001)
             print("🔍 [Intraday] 开始获取大盘指数数据...")
             try:
                 index_data = get_stock_realtime_tx('sh000001')
                 print(f"🔍 [Intraday] get_stock_realtime_tx('sh000001') 返回: {index_data}")
                 
                 if index_data:
                     market_index = {
                         'name': '大盘指数',
                         'price': index_data.get('price', 0),
                         'change_pct': index_data.get('change_pct', 0),
                         'trend': '未知' # derive roughly from change
                     }
                     if market_index['change_pct'] > 0.5: market_index['trend'] = '震荡向上'
                     elif market_index['change_pct'] < -0.5: market_index['trend'] = '加速下跌'
                     else: market_index['trend'] = '横盘震荡'
                     
                     print(f"✅ [Intraday] 大盘指数构建完成: {market_index}")
                 else:
                     print("⚠️ [Intraday] 无法获取上证指数实时数据 (get_stock_realtime_tx 返回 None)")
                     market_index = {'name': '大盘指数', 'price': 0, 'change_pct': 0, 'trend': '未知'}
             except Exception as e:
                 print(f"❌ [Intraday] 获取上证指数数据异常: {e}")
                 import traceback
                 traceback.print_exc()
                 market_index = {'name': '大盘指数', 'price': 0, 'change_pct': 0, 'trend': '未知'}

             # 2. Sector
             # load_sector_map / get_sector_performance 已在文件顶部从 data_fetcher 导入
             sector_map = load_sector_map()
             sector_name = sector_map.get(symbol, '未知板块')
             
             sector_info = {
                 'name': sector_name,
                 'change_pct': 0,
                 'rank': 'N/A'
             }
             if sector_name != '未知板块':
                 # Try to get sector performance
                 # Note: get_sector_performance might be slow or need optimization, 
                 # for now we assume it returns a float or 0
                 try:
                     sector_info['change_pct'] = get_sector_performance(sector_name)
                 except:
                     pass

             market_context = {
                 'market_index': market_index,
                 'sector_info': sector_info,
                 'sentiment': {
                     'limit_up_count': 'N/A', # Not available in realtime tx
                     'yesterday_limit_up': 'N/A'
                 }
             }
             print(f"🔍 [Intraday] market_context = {market_context}")

             analysis = generate_analysis(
                stock_info=stock_info,
                tech_data=tech_data,
                api_config=llm_config,
                analysis_type="intraday",
                realtime_data=rt_data,
                market_context=market_context
             )
             
             # 4. Stream Result
             import markdown
             html = markdown.markdown(analysis)
             
             # 5. Save to Intraday Log
             try:
                 save_intraday_log(
                     symbol=symbol,
                     price=rt_data.get('price', 0),
                     change_pct=rt_data.get('change_pct', 0),
                     analysis=analysis
                 )
                 yield f"data: {json.dumps({'type': 'step', 'content': '✅ 盘中分析已自动归档'})}\n\n"
             except Exception as save_e:
                 print(f"Failed to save intraday log: {save_e}")
             
             yield f"data: {json.dumps({'type': 'progress', 'value': 100, 'message': '分析完成'})}\n\n"
             yield f"data: {json.dumps({'type': 'result', 'content': analysis})}\n\n"
             yield f"data: {json.dumps({'type': 'final_html', 'content': html})}\n\n"
             yield f"data: {json.dumps({'type': 'complete', 'content': 'Done'})}\n\n"
             
        except Exception as e:
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'type': 'error', 'content': f'Error: {str(e)}'})}\n\n"

    return StreamingResponse(
        _stream_generator_intraday(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@app.post("/api/analyze/{symbol}/realtime")
async def analyze_stock_realtime(symbol: str, background_tasks: BackgroundTasks):
    """触发 AI 实时盘中分析"""
    if realtime_analysis_status.get(symbol, {}).get("status") == "running":
        return JSONResponse(status_code=400, content={"message": f"{symbol} 盘中分析正在运行中"})

    def _run_realtime_analysis():
        realtime_analysis_status[symbol] = {"status": "running", "message": f"正在进行盘中诊断 {symbol}...", "result": ""}
        
        try:
            from data_fetcher import fetch_data_dispatcher, calculate_start_date, fetch_stock_info
            from indicator_calc import calculate_indicators, get_latest_metrics
            from llm_analyst import generate_analysis
            from monitor_engine import get_realtime_data
            import markdown

            # 1. 获取股票信息
            # 首先尝试从持仓中获取，否则获取基本信息
            holdings = database.get_all_holdings()
            stock_info = next((h for h in holdings if h['symbol'] == symbol), None)
            
            if not stock_info:
                # 如果不在持仓中，获取基本信息
                basic_info = fetch_stock_info(symbol)
                if basic_info:
                     stock_info = {
                         'symbol': symbol,
                         'name': basic_info.get('name', symbol),
                         'asset_type': 'stock', # 如果需要，改进逻辑
                         'cost_price': None
                     }
                else:
                    realtime_analysis_status[symbol] = {
                        "status": "error",
                        "message": f"无法获取 {symbol} 信息",
                        "result": ""
                    }
                    return

            # 2. 获取历史背景（需要 MA20、MA60 等技术锚点）
            start_date = calculate_start_date()
            asset_type = stock_info.get('asset_type', 'stock')
            df = fetch_data_dispatcher(symbol, asset_type, start_date)
            
            latest_history = {}
            if df is not None and not df.empty:
                df = calculate_indicators(df)
                latest_history = get_latest_metrics(df, stock_info.get('cost_price', 0))
            
            # 3. Get Real-time Data (Crucial)
            # We also want Market Index status to pass to AI
            index_data = monitor_engine.get_market_index()
            
            realtime_dict = get_realtime_data([stock_info])
            realtime_data = realtime_dict.get(symbol)
            
            if not realtime_data:
                realtime_analysis_status[symbol] = {
                    "status": "error",
                    "message": "无法获取实时行情数据",
                    "result": ""
                }
                return

            # 将市场上下文注入 realtime_data 以供提示使用
            realtime_data['market_index_price'] = index_data.get('price', 'N/A')
            realtime_data['market_index_change'] = index_data.get('change_pct', 0)
            
            # 4. 加载 LLM 配置
            config = monitor_engine.load_config()
            provider = config.get('api', {}).get('provider', 'openai')
            llm_config = config.get(f'api_{provider}', config.get('llm_api', {}))
            
            if not llm_config.get('api_key'):
                 realtime_analysis_status[symbol] = {"status": "error", "message": "LLM API Key missing"}
                 return

            # 5. 生成分析（模式：实时）
            analysis = generate_analysis(
                stock_info=stock_info,
                tech_data=latest_history, # 来自历史的锚点
                api_config=llm_config,
                analysis_type="realtime",
                realtime_data=realtime_data
            )
            
            # 6. Result
            html_result = markdown.markdown(analysis, extensions=['tables'])
            
            realtime_analysis_status[symbol] = {
                "status": "success",
                "message": "诊断完成",
                "result": html_result,
                "raw": analysis,
                "timestamp": datetime.now().strftime("%H:%M:%S")
            }
            
        except Exception as e:
            print(f"Realtime analysis error: {e}")
            realtime_analysis_status[symbol] = {
                "status": "error",
                "message": str(e),
                "result": ""
            }

    background_tasks.add_task(_run_realtime_analysis)
    return {"status": "started", "message": f"开始诊断 {symbol}..."}

@app.get("/api/analyze/{symbol}/realtime/status")
async def get_realtime_analysis_status(symbol: str):
    return realtime_analysis_status.get(symbol, {"status": "idle"})

@app.post("/api/analyze/{symbol}/report")
async def generate_single_stock_report(symbol: str, background_tasks: BackgroundTasks):
    """生成单只股票的分析报告"""
    if single_analysis_status.get(symbol, {}).get("status") == "running":
        return JSONResponse(status_code=400, content={"message": f"{symbol} 分析任务已在运行中"})

    def _run_single_analysis():
        single_analysis_status[symbol] = {"status": "running", "message": f"正在分析 {symbol}...", "result": ""}

        try:
            # 导入所需的主模块
            from data_fetcher import fetch_data_dispatcher, calculate_start_date
            from indicator_calc import calculate_indicators, get_latest_metrics
            from llm_analyst import generate_analysis
            from monitor_engine import get_realtime_data
            import markdown

            # 1. 从持仓中获取股票信息
            holdings = database.get_all_holdings()
            stock_info = next((h for h in holdings if h['symbol'] == symbol), None)

            if not stock_info:
                single_analysis_status[symbol] = {
                    "status": "error",
                    "message": f"未找到股票 {symbol} 在持仓列表中",
                    "result": ""
                }
                return

            # 2. 获取历史数据
            start_date = calculate_start_date()
            asset_type = stock_info.get('asset_type', 'stock')
            df = fetch_data_dispatcher(symbol, asset_type, start_date)

            if df is None or df.empty:
                single_analysis_status[symbol] = {
                    "status": "error",
                    "message": f"无法获取 {symbol} 的历史数据",
                    "result": ""
                }
                return

            # 3. 计算指标
            df = calculate_indicators(df)

            # 4. 获取最新历史指标（基于昨日收盘价的技术指标）
            latest = get_latest_metrics(df, stock_info.get('cost_price', 0))

            # 5. 获取实时价格
            realtime_dict = get_realtime_data([stock_info])
            realtime_data = realtime_dict.get(symbol)

            # 6. 如果可用，用实时价格更新最新数据
            if realtime_data and realtime_data.get('price'):
                print(f"📊 {symbol} - 历史收盘价: {latest.get('close')}, 实时价格: {realtime_data.get('price')}")
                # 用实时价格覆盖收盘价
                latest['close'] = round(realtime_data.get('price'), 3)
                latest['realtime_price'] = round(realtime_data.get('price'), 3)
                latest['change_pct_today'] = round(realtime_data.get('change_pct', 0), 2)
                # 因为有实时数据，将日期更新为今天
                latest['date'] = datetime.now().strftime('%Y-%m-%d')

                # 用实时价格重新计算盈亏
                if stock_info.get('cost_price'):
                    cost_price = stock_info['cost_price']
                    profit_loss_pct = ((latest['close'] - cost_price) / cost_price) * 100
                    latest['profit_loss_pct'] = round(profit_loss_pct, 2)
            else:
                print(f"⚠️ {symbol} - 无法获取实时价格，使用历史收盘价: {latest.get('close')}")

            # 7. 加载 LLM 配置
            config = monitor_engine.load_config()

            # 根据提供商动态解析 API 配置
            provider = config.get('api', {}).get('provider', 'openai')
            llm_config = config.get(f'api_{provider}', config.get('llm_api', {}))

            if not llm_config.get('api_key'):
                single_analysis_status[symbol] = {
                    "status": "error",
                    "message": f"LLM API 配置缺失 (Provider: {provider})",
                    "result": ""
                }
                return

            # 8. 生成 AI 分析（使用包含实时价格的latest数据）
            analysis = generate_analysis(
                stock_info=stock_info,
                tech_data=latest,
                api_config=llm_config,
                analysis_type="holding"
            )

            # 9. 格式化结果
            from llm_analyst import format_stock_section
            formatted_report = format_stock_section(stock_info, latest, analysis)

            # 转换为 HTML 以供前端显示
            html_result = markdown.markdown(formatted_report, extensions=['tables', 'fenced_code'])

            # 10. 将分析保存到数据库（保存实时价格）
            analysis_data = {
                'price': latest.get('close', 0),  # 现在是实时价格
                'ma20': latest.get('ma20', 0),
                'trend_signal': latest.get('ma_arrangement', '未知'),
                'composite_score': latest.get('composite_score', 0),
                'ai_analysis': formatted_report  # 保存完整的 markdown 报告
            }
            # 确保价格有效 (latest['close'] 已经用 RT 价格更新（如果可用），但如果 RT 为 0，如果有需要则使用历史)
            if analysis_data['price'] == 0 and latest.get('realtime_price', 0) == 0:
                 # 检查最新的原始收盘价是否非零 (来自历史)
                 # 'latest' 在上面已更新，所以如果需要检查原始收盘价，但 fetch 逻辑处理 0 跳过。
                 # 如果需要，这只是一个安全检查。
                 pass

            analysis_date = datetime.now().strftime('%Y-%m-%d')

            try:
                database.save_holding_analysis(symbol, analysis_date, analysis_data, mode="single_prompt")
                print(f"✅ Analysis for {symbol} saved to database.")
            except Exception as db_e:
                print(f"⚠️ Failed to save analysis to DB: {db_e}")

            single_analysis_status[symbol] = {
                "status": "success",
                "message": f"{symbol} 分析完成",
                "result": html_result,
                "raw": formatted_report
            }

        except Exception as e:
            single_analysis_status[symbol] = {
                "status": "error",
                "message": f"分析失败: {str(e)}",
                "result": ""
            }

    background_tasks.add_task(_run_single_analysis)
    return {"status": "started", "message": f"🤖 正在生成 {symbol} 的分析报告..."}

@app.get("/api/analyze/{symbol}/status")
async def get_single_analysis_status(symbol: str):
    """获取特定股票的分析状态"""
    status = single_analysis_status.get(symbol, {"status": "idle", "message": "", "result": ""})
    return status

@app.get("/api/analyze/{symbol}/dates")
async def get_analysis_dates(symbol: str, mode: str = 'multi_agent'):
    """获取股票的可用分析日期"""
    dates = database.get_analysis_dates_for_stock(symbol, mode=mode)
    return {"status": "success", "dates": dates}

@app.get("/api/analyze/{symbol}/history")
async def get_analysis_history(symbol: str, date: str = None, mode: str = 'multi_agent'):
    """获取特定日期的分析报告（如果没有日期,则获取最新的）"""
    try:
        import markdown
        
        # 特殊处理：如果是盘中分析模式，从 intraday_logs 表查询
        if mode == 'intraday':
            try:
                from database import get_intraday_log
                
                # date 参数对于 intraday 是 analysis_time 的格式 (可选)
                intraday_result = get_intraday_log(symbol, analysis_time=date)
                
                if intraday_result:
                    # 将 markdown 转换为 HTML
                    html_result = markdown.markdown(intraday_result['ai_content'], extensions=['tables', 'fenced_code'])
                    
                    # 尝试获取股票名称
                    holdings = database.get_all_holdings()
                    stock_info = next((h for h in holdings if h['symbol'] == symbol), None)
                    stock_name = stock_info['name'] if stock_info else symbol
                    
                    return {
                        "status": "success",
                        "data": {
                            "symbol": symbol,
                            "name": stock_name,
                            "analysis_date": intraday_result['analysis_time'],  # 盘中分析使用 analysis_time
                            "price": intraday_result['price'],
                            "change_pct": intraday_result['change_pct'],
                            "ma20": 0,  # 盘中分析不存储 MA20
                            "trend_signal": "盘中",
                            "composite_score": 0,  # 盘中分析不使用综合评分
                            "ai_analysis": intraday_result['ai_content'],
                            "html": html_result,
                            "mode": "intraday"
                        }
                    }
                else:
                    return {"status": "no_data", "message": f"暂无 {symbol} 的盘中分析记录"}
                    
            except Exception as intraday_error:
                print(f"❌ Error fetching intraday log for {symbol}: {intraday_error}")
                return {"status": "error", "message": f"查询盘中分析失败: {str(intraday_error)}"}
        
        # 获取持仓以查找股票信息
        holdings = database.get_all_holdings()
        stock_info = next((h for h in holdings if h['symbol'] == symbol), None)

        # 如果不在持仓中，它可能是一个候选选择
        if not stock_info:
             # 尝试在每日每日精选逻辑中查找（由用法暗示）或者如果能找到分析就继续
             pass

        # 首先尝试从 holding_analysis 表获取分析
        
        try:
            result = database.get_holding_analysis(symbol, analysis_date=date, mode=mode)

            if result:
                # 将 markdown 转换为 HTML
                html_result = markdown.markdown(result['ai_analysis'], extensions=['tables', 'fenced_code'])
                
                name = stock_info['name'] if stock_info else result.get('name', symbol)

                return {
                    "status": "success",
                    "data": {
                        "symbol": symbol,
                        "name": name,
                        "analysis_date": result['analysis_date'],
                        "price": result['price'],
                        "ma20": result['ma20'],
                        "trend_signal": result['trend_signal'],
                        "composite_score": result['composite_score'],
                        "ai_analysis": result['ai_analysis'],
                        "html": html_result,
                        "mode": mode
                    }
                }
            
            # 如果没有持仓分析，尝试回退到 daily_selections（用于选股器候选者）
            # 这对我们最初只有技术分析的新需求很重要
            # 我们将“候选”分析视为特殊回退
            
            selection = database.get_daily_selection(symbol, selection_date=date)
            if selection:
                # ai_analysis 可能已经是 HTML（如果来自多智能体）或 Markdown（如果来自候选分析）
                content = selection['ai_analysis']
                is_html_likely = content.strip().startswith('<') or "div" in content or "span" in content
                
                html_result = content if is_html_likely else markdown.markdown(content, extensions=['tables', 'fenced_code'])
                 
                return {
                    "status": "success",
                    "data": {
                        "symbol": symbol,
                        "name": selection['name'],
                        "analysis_date": selection['selection_date'],
                        "price": selection.get('close_price', 0),
                        "ma20": 0, # 不直接存储在精选表中
                        "trend_signal": "Candidate",
                        "composite_score": selection['composite_score'],
                        "ai_analysis": content,
                        "html": html_result,
                        "mode": "candidate"
                    }
                }

            return {"status": "no_data", "message": f"暂无 {symbol} 的 {mode} 分析报告"}

        except Exception as db_error:
            print(f"❌ Database query error for {symbol}: {db_error}")
            return {"status": "error", "message": f"数据库查询失败: {str(db_error)}"}

    except Exception as e:
        print(f"❌ Error getting analysis for {symbol}: {e}")
        return {"status": "error", "message": f"获取失败: {str(e)}"}

@app.get("/api/analyze/{symbol}/latest")
async def get_latest_analysis(symbol: str, mode: str = 'multi_agent'):
    """最新分析的旧端点"""
    return await get_analysis_history(symbol, date=None, mode=mode)

# --- 候选股票分析 ---

candidate_analysis_status = {}  # {symbol: {"status": "idle"|"running"|"success"|"error", "message": "", "result": ""}}

@app.post("/api/analyze/candidate/{symbol}")
async def analyze_candidate_stock(symbol: str, background_tasks: BackgroundTasks):
    """分析候选股票的买入机会（使用选股策略）"""
    if candidate_analysis_status.get(symbol, {}).get("status") == "running":
        return JSONResponse(status_code=400, content={"message": f"{symbol} 分析任务已在运行中"})

    def _run_candidate_analysis():
        candidate_analysis_status[symbol] = {"status": "running", "message": f"正在分析 {symbol}...", "result": ""}

        try:
            # Import main modules needed
            from data_fetcher import fetch_data_dispatcher, calculate_start_date, fetch_stock_info
            from indicator_calc import calculate_indicators, get_latest_metrics
            from llm_analyst import generate_analysis
            from monitor_engine import get_realtime_data
            import markdown

            # 1. 获取股票基本信息（从实时数据或搜索获取）
            stock_info_basic = fetch_stock_info(symbol)

            if not stock_info_basic:
                candidate_analysis_status[symbol] = {
                    "status": "error",
                    "message": f"无法找到股票 {symbol} 的信息",
                    "result": ""
                }
                return

            stock_info = {
                'symbol': symbol,
                'name': stock_info_basic.get('name', symbol),
                'asset_type': 'stock',  # 候选股默认为stock
                'cost_price': None  # 候选股没有成本价
            }

            # 2. Fetch historical data
            start_date = calculate_start_date()
            asset_type = stock_info.get('asset_type', 'stock')
            df = fetch_data_dispatcher(symbol, asset_type, start_date)

            if df is None or df.empty:
                candidate_analysis_status[symbol] = {
                    "status": "error",
                    "message": f"无法获取 {symbol} 的历史数据",
                    "result": ""
                }
                return

            # 3. Calculate indicators
            df = calculate_indicators(df)

            # 4. 获取最新历史指标（基于昨日收盘价的技术指标）
            latest = get_latest_metrics(df, cost_price=None)
            
            # --- 4.5 尝试从 daily_selections 恢复元数据 (排名，情绪等) ---
            from database import get_daily_selection
            
            # 尝试今天或最近
            selection_record = get_daily_selection(symbol, None)
            if selection_record and selection_record.get('ai_analysis'):
                import re
                import json
                
                # 检查隐藏的元数据
                # Format: <!-- METADATA: {"rank_in_sector": 5, ...} -->
                match = re.search(r'<!-- METADATA: (.*?) -->', selection_record['ai_analysis'])
                if match:
                    try:
                        meta_str = match.group(1)
                        metadata = json.loads(meta_str)
                        print(f"💡 Recovered metadata for {symbol}: {metadata.keys()}")
                        
                        # 合并到最新指标
                        for k, v in metadata.items():
                            latest[k] = v
                    except Exception as meta_e:
                        print(f"⚠️ Failed to parse metadata: {meta_e}")

            # 5. 获取实时价格
            realtime_dict = get_realtime_data([stock_info])
            realtime_data = realtime_dict.get(symbol)
            
            # --- 5.1 注入板块数据（修复候选提示中缺失的数据） ---
            try:
                sector_map = load_sector_map()
                sector_name = sector_map.get(symbol, 'N/A')
                
                if realtime_data:
                    realtime_data['sector'] = sector_name
                    # 如果需要，也注入到最新数据中以保持一致性，但 Prompt 通常使用 realtime_data 来获取板块
                    latest['sector'] = sector_name
                    
                    if sector_name != 'N/A':
                         # 使用导入的 get_sector_performance
                         sector_change = get_sector_performance(sector_name)
                         realtime_data['sector_change'] = sector_change
                         latest['sector_change'] = sector_change
                    else:
                         realtime_data['sector_change'] = 0
                         latest['sector_change'] = 0
                    
                    # 排名逻辑（目前占位，因为跳过了昂贵的计算）
                    realtime_data['rank_in_sector'] = 'N/A'
                    latest['rank_in_sector'] = 'N/A'
            except Exception as sec_e:
                print(f"⚠️ Sector fetch failed for {symbol}: {sec_e}")

            # 6. Update latest with realtime price if available
            if realtime_data and realtime_data.get('price'):
                print(f"📊 {symbol} - 历史收盘价: {latest.get('close')}, 实时价格: {realtime_data.get('price')}")
                latest['close'] = round(realtime_data.get('price'), 3)
                latest['realtime_price'] = round(realtime_data.get('price'), 3)
                latest['change_pct_today'] = round(realtime_data.get('change_pct', 0), 2)
                # Update date to today since we have realtime data
                latest['date'] = datetime.now().strftime('%Y-%m-%d')
            else:
                print(f"⚠️ {symbol} - 无法获取实时价格，使用历史收盘价: {latest.get('close')}")

            # 7. Load LLM config
            config = monitor_engine.load_config()

            # Resolve API config dynamically based on provider
            provider = config.get('api', {}).get('provider', 'openai')
            llm_config = config.get(f'api_{provider}', config.get('llm_api', {}))

            if not llm_config.get('api_key'):
                candidate_analysis_status[symbol] = {
                    "status": "error",
                    "message": f"LLM API 配置缺失 (Provider: {provider})",
                    "result": ""
                }
                return

            # 8. 生成 AI 分析（使用候选股策略 - analysis_type="candidate")
            analysis = generate_analysis(
                stock_info=stock_info,
                tech_data=latest,
                api_config=llm_config,
                analysis_type="candidate"  # 🔥 使用选股策略
            )

            # 9. 格式化结果
            from llm_analyst import format_stock_section
            formatted_report = format_stock_section(stock_info, latest, analysis)

            # 转换为 HTML 以供前端显示
            html_result = markdown.markdown(formatted_report, extensions=['tables', 'fenced_code'])

            # 10. 可选地保存到数据库（保存到候选股表）
            try:
                selection_data = {
                    'symbol': stock_info['symbol'],
                    'name': stock_info['name'],
                    'close_price': latest['close'],
                    'volume_ratio': latest.get('volume_ratio', 0),
                    'composite_score': latest.get('composite_score', 0),
                    'ai_analysis': formatted_report
                }
                analysis_date = datetime.now().strftime('%Y-%m-%d')
                database.save_daily_selection(analysis_date, selection_data)
                print(f"✅ Candidate analysis for {symbol} saved to database.")
            except Exception as db_e:
                print(f"⚠️ Failed to save candidate analysis to DB: {db_e}")

            candidate_analysis_status[symbol] = {
                "status": "success",
                "message": f"{symbol} 候选股分析完成",
                "result": html_result,
                "raw": formatted_report,
                "data": {
                    "symbol": symbol,
                    "name": stock_info['name'],
                    "price": latest['close'],
                    "score": latest.get('composite_score', 0)
                }
            }

        except Exception as e:
            candidate_analysis_status[symbol] = {
                "status": "error",
                "message": f"分析失败: {str(e)}",
                "result": ""
            }
            print(f"❌ Candidate analysis error for {symbol}: {e}")

    background_tasks.add_task(_run_candidate_analysis)
    return {"status": "started", "message": f"🤖 正在分析候选股 {symbol}..."}

@app.get("/api/analyze/candidate/{symbol}/status")
async def get_candidate_analysis_status(symbol: str):
    """获取特定股票的候选分析状态"""
    status = candidate_analysis_status.get(symbol, {"status": "idle", "message": "", "result": ""})
    return status

# --- 策略管理 API ---

@app.get("/api/strategies")
async def list_strategies():
    """列出所有策略"""
    return database.get_all_strategies()

@app.get("/api/strategies/{slug}")
async def get_strategy(slug: str):
    """获取包括参数在内的策略详情"""
    strategy = database.get_strategy_by_slug(slug)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return strategy

class StrategyTemplateUpdate(BaseModel):
    template: str

@app.post("/api/strategies/{id}/template")
async def update_strategy_template(id: int, update: StrategyTemplateUpdate):
    """更新策略提示模板"""
    success = database.update_strategy_template(id, update.template)
    if success:
        return {"status": "success", "message": "Updated template"}
    raise HTTPException(status_code=400, detail="Update failed")

class StrategyParamUpdate(BaseModel):
    key: str
    value: str

@app.post("/api/strategies/{id}/params")
async def update_strategy_param(id: int, param: StrategyParamUpdate):
    """更新策略参数"""
    success = database.update_strategy_param(id, param.key, param.value)
    if success:
        return {"status": "success", "message": f"Updated param {param.key}"}
    raise HTTPException(status_code=400, detail="Update failed")

# --- 静态文件和 SPA 回退（必须在所有 API 路由之后） ---

if USE_VUE_FRONTEND:
    # 挂载 Vue dist 文件夹以获取静态资源（js、css、图片等）
    app.mount("/assets", StaticFiles(directory=str(VUE_FRONTEND_PATH / "assets")), name="vue-assets")
    print("🚀 Using Vue frontend (dist) for static assets")

    @app.get("/{full_path:path}", response_class=HTMLResponse)
    async def serve_spa_fallback(full_path: str):
        """为所有非 API 路由提供 index.html（SPA 回退）"""
        # 如果是 API 路由则不拦截
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API route not found")

        index_file = VUE_FRONTEND_PATH / "index.html"
        with open(index_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), status_code=200)
else:
    # 使用 Jinja2 模板 (传统模式)
    @app.get("/", response_class=HTMLResponse)
    async def read_root(request: Request):
        """渲染主仪表板"""
        return templates.TemplateResponse("index.html", {
            "request": request,
            "title": "A-Share Monitor"
        })

    @app.get("/strategies", response_class=HTMLResponse)
    async def strategy_config_page(request: Request):
        """渲染策略配置页面"""
        return templates.TemplateResponse("strategies.html", {
            "request": request,
            "title": "策略配置中心"
        })

if __name__ == "__main__":
    uvicorn.run("web_server:app", host="0.0.0.0", port=8100, reload=True, access_log=False)