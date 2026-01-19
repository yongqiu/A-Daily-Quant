"""
Web Server for A-Share Strategy Monitor
Exposes API for frontend and runs background monitoring tasks.
"""
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
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
from collections import deque
from typing import Optional

from monitor_engine import MonitorEngine
from data_fetcher import fetch_data_dispatcher, calculate_start_date, fetch_stock_info
import database  # Add database import

app = FastAPI(title="A-Share Strategy Monitor")

# Initialize Engine
monitor_engine = MonitorEngine()

# Setup Templates
templates = Jinja2Templates(directory="templates")

# Configure Logging (Suppress Uvicorn Access Logs)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("uvicorn.error").setLevel(logging.WARNING)

# Global State
market_state = {
    "index": {"name": "初始化中...", "price": 0, "change_pct": 0},
    "stocks": [],
    "last_update": "N/A",
    "is_monitoring": False, # Monitoring Switch - 默认关闭，由用户手动开启
    "config": {
        "update_interval": 10  # Default
    }
}

async def market_data_loop():
    """Infinite loop to update data"""
    print("🚀 Background monitoring task started (默认暂停，等待用户开启).")
    while True:
        try:
            # Check Switch
            if not market_state["is_monitoring"]:
                market_state["last_update"] = "监控已暂停 - 点击按钮开启"
                await asyncio.sleep(2)
                continue

            # Refresh Config
            config = monitor_engine.load_config() # Reload config hot
            interval = config.get('monitor', {}).get('update_interval_seconds', 10)
            market_state["config"]["update_interval"] = interval
            
            # 1. Update Index
            # Check if monitor_engine has method, otherwise add it
            if hasattr(monitor_engine, 'load_config') is False:
                # Hot-patching purely for robustness if file changed out of order,
                # but locally monitor_engine.load_config exists as global function
                # We need to call module level function or make it static
                from monitor_engine import load_config as _load_config
                monitor_engine.load_config = lambda: _load_config()
        
            index_data = monitor_engine.get_market_index()
            market_state["index"] = index_data
            
            # 2. Update Stocks
            stocks_data = monitor_engine.run_check()
            market_state["stocks"] = stocks_data
            
            market_state["last_update"] = datetime.now().strftime("%H:%M:%S")
            print(f"🔄 Market data updated at {market_state['last_update']} (Next update in {interval}s)")
            
            await asyncio.sleep(interval)
            
        except Exception as e:
            print(f"❌ Error in background loop: {e}")
            await asyncio.sleep(10) # Retry delay

@app.on_event("startup")
async def startup_event():
    """Run initial check on startup"""
    monitor_engine.refresh_targets()
    # Start the background loop (默认暂停状态)
    asyncio.create_task(market_data_loop())
    print("📋 监控系统已就绪，等待用户手动开启...")

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Render the main dashboard"""
    return templates.TemplateResponse("index.html", {
        "request": request,
        "title": "A-Share Monitor"
    })

@app.get("/strategies", response_class=HTMLResponse)
async def strategy_config_page(request: Request):
    """Render the strategy configuration page"""
    return templates.TemplateResponse("strategies.html", {
        "request": request,
        "title": "策略配置中心"
    })

@app.get("/api/status")
async def get_status():
    """API called by frontend poller"""
    # Return cached state immediately (non-blocking)
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
    """Search stock information by symbol"""
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
    """Get all holdings from database with latest analysis"""
    today = datetime.now().strftime('%Y-%m-%d')
    holdings = database.get_all_holdings(analysis_date=today)
    # Enrich with latest analysis if needed, or frontend can correlate
    return holdings

@app.post("/api/holdings")
async def add_holding(holding: HoldingBase):
    """Add a new holding"""
    # If name is empty, try to fetch it? For now let client provide it or default
    if not holding.name:
        # Simple fallback or let it be empty
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
        return {"status": "success", "message": f"Added {holding.symbol}"}
    else:
        raise HTTPException(status_code=400, detail="Failed to add holding (already exists?)")

@app.put("/api/holdings/{symbol}")
async def update_holding(symbol: str, holding: HoldingUpdate):
    """Update holding details"""
    success = database.update_holding(
        symbol,
        cost_price=holding.cost_price,
        position_size=holding.position_size
    )
    if success:
        return {"status": "success", "message": f"Updated {symbol}"}
    else:
        raise HTTPException(status_code=400, detail="Failed to update holding")

@app.delete("/api/holdings/{symbol}")
async def delete_holding(symbol: str):
    """Remove a holding"""
    success = database.remove_holding(symbol)
    if success:
        monitor_engine.refresh_targets()
        return {"status": "success", "message": f"Removed {symbol}"}
    else:
        raise HTTPException(status_code=404, detail="Holding not found")

@app.get("/api/selections")
async def get_selections(date: str = None):
    """Get daily selections from database"""
    # If date is not provided, database layer handles retrieving the latest
    return database.get_daily_selections(date)

@app.post("/api/monitor/toggle")
async def toggle_monitor():
    """Toggle monitoring on/off"""
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

@app.post("/api/analyze/{symbol}")
async def analyze_stock(symbol: str, background_tasks: BackgroundTasks):
    """Trigger AI analysis for a specific stock"""
    def _run_analysis():
        result = monitor_engine.run_ai_analysis_for_target(symbol)
        # Force a quick update of market state with new AI result
        market_state["stocks"] = monitor_engine.run_check()
        
    background_tasks.add_task(_run_analysis)
    return {"status": "started", "message": f"🤖 AI正在分析 {symbol}，请稍候..."}

@app.get("/api/kline/{symbol}")
async def get_kline_data(symbol: str):
    """Fetch K-line data for charts"""
    # 1. Find the target to know its asset type
    target = next((t for t in monitor_engine.targets if t['symbol'] == symbol), None)
    
    asset_type = 'stock' # Default
    if target:
        asset_type = target.get('asset_type', 'stock')
    
    # 2. Convert raw K-line dataframe to list format for charts (e.g. ECharts)
    # [Date, Open, Close, Low, High, Volume]
    
    try:
        days = 120
        # If asset_type is crypto, data_fetcher might need tuning or use separate calls,
        # but fetch_data_dispatcher handles it.
        
        start_date = calculate_start_date(days)
        df = fetch_data_dispatcher(symbol, asset_type, start_date)
        
        if df is None or df.empty:
            return {"status": "error", "message": "No data found"}
            
        # Format for ECharts (Category Axis + Data Series)
        # categoryData: ['2023-01-01', ...]
        # values: [[open, close, low, high, vol], ...]
        
        dates = df['date'].dt.strftime('%Y-%m-%d').tolist()
        
        # ECharts Candle Format: [Open, Close, Lowest, Highest]
        # Our DF: open, close, high, low
        # Note order!
        
        values = []
        volumes = []
        
        # Iteration is slow for huge data but 120 rows is fine
        for _, row in df.iterrows():
            values.append([
                row['open'],
                row['close'],
                row['low'],
                row['high']
            ])
            volumes.append(row['volume'])
            
        return {
            "status": "success",
            "symbol": symbol,
            "name": target['name'] if target else symbol,
            "dates": dates,
            "values": values,
            "volumes": volumes
        }
        
    except Exception as e:
        print(f"Kline Error: {e}")
        return {"status": "error", "message": str(e)}

# --- Report Management ---

@app.get("/api/report/latest")
async def get_latest_report():
    """Get the content of the latest strategy report (Combines sections if available)"""
    report_dir = "reports"
    if not os.path.exists(report_dir):
        return {"content": "<h3>暂无日报</h3>", "filename": None}

    # Try to find date from latest full or section file
    all_files = os.listdir(report_dir)
    # Match dates like 20250101
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
    
    # Try reading individual sections first
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

    # Fallback to Full Legacy File
    full_path = os.path.join(report_dir, f"daily_strategy_full_{latest_date}.md")
    if os.path.exists(full_path):
        # ... logic as before for legacy split ...
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

# Report Status & Logs
report_generation_status = {"status": "idle", "message": ""}
report_logs = deque(maxlen=200) # Store last 200 lines of logs

@app.post("/api/report/generate")
async def generate_report(background_tasks: BackgroundTasks, section: str = "all"):
    """Trigger daily report generation script (optional section)"""
    if report_generation_status["status"] == "running":
        return JSONResponse(status_code=400, content={"message": "生成任务已在运行中"})
    
    def _run_generation():
        report_generation_status["status"] = "running"
        report_generation_status["message"] = f"正在启动生成 ({section})..."
        report_logs.clear() # Clear old logs
        
        try:
            # Run main.py as a subprocess with Popen to stream stdout
            # Use sys.executable to ensure we use the same python interpreter (venv)
            cmd = [sys.executable, "-u", "main.py", "--section", section]
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            # Read stdout line by line
            for line in process.stdout:
                line = line.strip()
                if line:
                    print(f"[Report] {line}") # Also print to backend console
                    report_logs.append(line)
                    # Update status message with latest log
                    report_generation_status["message"] = line
            
            process.wait()
            
            if process.returncode == 0:
                report_generation_status["status"] = "success"
                report_generation_status["message"] = "生成成功！请刷新查看。"
                # Refresh targets if new candidates found
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

# --- Single Stock Analysis ---

single_analysis_status = {}  # {symbol: {"status": "idle"|"running"|"success"|"error", "message": "", "result": ""}}
realtime_analysis_status = {} # {symbol: {"status": "idle"|"running"|"success"|"error", "message": "", "result": ""}}

@app.post("/api/analyze/{symbol}/realtime")
async def analyze_stock_realtime(symbol: str, background_tasks: BackgroundTasks):
    """Trigger AI Real-time Intraday Analysis"""
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

            # 1. Get stock info
            # Try to get from holdings first, else fetch basic info
            holdings = database.get_all_holdings()
            stock_info = next((h for h in holdings if h['symbol'] == symbol), None)
            
            if not stock_info:
                # If not in holdings, fetch basic info
                basic_info = fetch_stock_info(symbol)
                if basic_info:
                     stock_info = {
                         'symbol': symbol,
                         'name': basic_info.get('name', symbol),
                         'asset_type': 'stock', # Improve logic if needed
                         'cost_price': None
                     }
                else:
                    realtime_analysis_status[symbol] = {
                        "status": "error",
                        "message": f"无法获取 {symbol} 信息",
                        "result": ""
                    }
                    return

            # 2. Fetch historical context (need technical anchors like MA20, MA60)
            start_date = calculate_start_date(120)
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

            # Inject market context into realtime_data for the prompt
            realtime_data['market_index_price'] = index_data.get('price', 'N/A')
            realtime_data['market_index_change'] = index_data.get('change_pct', 0)
            
            # 4. Load LLM Config
            config = monitor_engine.load_config()
            provider = config.get('api', {}).get('provider', 'openai')
            llm_config = config.get(f'api_{provider}', config.get('llm_api', {}))
            
            if not llm_config.get('api_key'):
                 realtime_analysis_status[symbol] = {"status": "error", "message": "LLM API Key missing"}
                 return

            # 5. Generate Analysis (Mode: realtime)
            analysis = generate_analysis(
                stock_info=stock_info,
                tech_data=latest_history, # Anchors from history
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
    """Generate analysis report for a single stock"""
    if single_analysis_status.get(symbol, {}).get("status") == "running":
        return JSONResponse(status_code=400, content={"message": f"{symbol} 分析任务已在运行中"})

    def _run_single_analysis():
        single_analysis_status[symbol] = {"status": "running", "message": f"正在分析 {symbol}...", "result": ""}

        try:
            # Import main modules needed
            from data_fetcher import fetch_data_dispatcher, calculate_start_date
            from indicator_calc import calculate_indicators, get_latest_metrics
            from llm_analyst import generate_analysis
            from monitor_engine import get_realtime_data
            import markdown

            # 1. Get stock info from holdings
            holdings = database.get_all_holdings()
            stock_info = next((h for h in holdings if h['symbol'] == symbol), None)

            if not stock_info:
                single_analysis_status[symbol] = {
                    "status": "error",
                    "message": f"未找到股票 {symbol} 在持仓列表中",
                    "result": ""
                }
                return

            # 2. Fetch historical data
            start_date = calculate_start_date(120)
            asset_type = stock_info.get('asset_type', 'stock')
            df = fetch_data_dispatcher(symbol, asset_type, start_date)

            if df is None or df.empty:
                single_analysis_status[symbol] = {
                    "status": "error",
                    "message": f"无法获取 {symbol} 的历史数据",
                    "result": ""
                }
                return

            # 3. Calculate indicators
            df = calculate_indicators(df)

            # 4. Get latest historical metrics (基于昨日收盘价的技术指标)
            latest = get_latest_metrics(df, stock_info.get('cost_price', 0))

            # 5. Get realtime price (获取实时价格)
            realtime_dict = get_realtime_data([stock_info])
            realtime_data = realtime_dict.get(symbol)

            # 6. Update latest with realtime price if available
            if realtime_data and realtime_data.get('price'):
                print(f"📊 {symbol} - 历史收盘价: {latest.get('close')}, 实时价格: {realtime_data.get('price')}")
                # Override close price with realtime price
                latest['close'] = round(realtime_data.get('price'), 3)
                latest['realtime_price'] = round(realtime_data.get('price'), 3)
                latest['change_pct_today'] = round(realtime_data.get('change_pct', 0), 2)
                # Update date to today since we have realtime data
                latest['date'] = datetime.now().strftime('%Y-%m-%d')

                # Recalculate profit/loss with realtime price
                if stock_info.get('cost_price'):
                    cost_price = stock_info['cost_price']
                    profit_loss_pct = ((latest['close'] - cost_price) / cost_price) * 100
                    latest['profit_loss_pct'] = round(profit_loss_pct, 2)
            else:
                print(f"⚠️ {symbol} - 无法获取实时价格，使用历史收盘价: {latest.get('close')}")

            # 7. Load LLM config
            config = monitor_engine.load_config()

            # Resolve API config dynamically based on provider
            provider = config.get('api', {}).get('provider', 'openai')
            llm_config = config.get(f'api_{provider}', config.get('llm_api', {}))

            if not llm_config.get('api_key'):
                single_analysis_status[symbol] = {
                    "status": "error",
                    "message": f"LLM API 配置缺失 (Provider: {provider})",
                    "result": ""
                }
                return

            # 8. Generate AI analysis (使用包含实时价格的latest数据)
            analysis = generate_analysis(
                stock_info=stock_info,
                tech_data=latest,
                api_config=llm_config,
                analysis_type="holding"
            )

            # 9. Format result
            from llm_analyst import format_stock_section
            formatted_report = format_stock_section(stock_info, latest, analysis)

            # Convert to HTML for frontend display
            html_result = markdown.markdown(formatted_report, extensions=['tables', 'fenced_code'])

            # 10. Save analysis to database (保存实时价格)
            analysis_data = {
                'price': latest.get('close', 0),  # 现在是实时价格
                'ma20': latest.get('ma20', 0),
                'trend_signal': latest.get('ma_arrangement', '未知'),
                'composite_score': latest.get('composite_score', 0),
                'ai_analysis': formatted_report  # Save the full markdown report
            }
            analysis_date = datetime.now().strftime('%Y-%m-%d')

            try:
                database.save_holding_analysis(symbol, analysis_date, analysis_data)
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
    """Get analysis status for a specific stock"""
    status = single_analysis_status.get(symbol, {"status": "idle", "message": "", "result": ""})
    return status

@app.get("/api/analyze/{symbol}/latest")
async def get_latest_analysis(symbol: str):
    """Get the latest analysis report for a specific stock from database"""
    try:
        # Get holdings to find stock info
        holdings = database.get_all_holdings()
        stock_info = next((h for h in holdings if h['symbol'] == symbol), None)

        if not stock_info:
            return {"status": "not_found", "message": f"股票 {symbol} 不在持仓列表中"}

        # Try to get analysis from database
        try:
            conn = database.get_connection()
            cursor = conn.cursor()

            # Query for the most recent analysis
            cursor.execute("""
                SELECT analysis_date, price, ma20, trend_signal, composite_score, ai_analysis
                FROM holding_analysis
                WHERE symbol = %s
                ORDER BY analysis_date DESC
                LIMIT 1
            """, (symbol,))

            result = cursor.fetchone()
            cursor.close()
            conn.close()

            if result:
                import markdown
                # Convert markdown to HTML
                html_result = markdown.markdown(result['ai_analysis'], extensions=['tables', 'fenced_code'])

                return {
                    "status": "success",
                    "data": {
                        "symbol": symbol,
                        "name": stock_info['name'],
                        "analysis_date": result['analysis_date'].strftime('%Y-%m-%d') if hasattr(result['analysis_date'], 'strftime') else str(result['analysis_date']),
                        "price": result['price'],
                        "ma20": result['ma20'],
                        "trend_signal": result['trend_signal'],
                        "composite_score": result['composite_score'],
                        "ai_analysis": result['ai_analysis'],
                        "html": html_result
                    }
                }
            else:
                return {"status": "no_data", "message": f"暂无 {symbol} 的分析报告"}

        except Exception as db_error:
            print(f"❌ Database query error for {symbol}: {db_error}")
            return {"status": "error", "message": f"数据库查询失败: {str(db_error)}"}

    except Exception as e:
        print(f"❌ Error getting latest analysis for {symbol}: {e}")
        return {"status": "error", "message": f"获取失败: {str(e)}"}

# --- Candidate Stock Analysis ---

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

            # 1. Get stock basic info (从实时数据或搜索获取)
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
            start_date = calculate_start_date(120)
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

            # 4. Get latest historical metrics (基于昨日收盘价的技术指标)
            latest = get_latest_metrics(df, cost_price=None)

            # 5. Get realtime price (获取实时价格)
            realtime_dict = get_realtime_data([stock_info])
            realtime_data = realtime_dict.get(symbol)

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

            # 8. Generate AI analysis (使用候选股策略 - analysis_type="candidate")
            analysis = generate_analysis(
                stock_info=stock_info,
                tech_data=latest,
                api_config=llm_config,
                analysis_type="candidate"  # 🔥 使用选股策略
            )

            # 9. Format result
            from llm_analyst import format_stock_section
            formatted_report = format_stock_section(stock_info, latest, analysis)

            # Convert to HTML for frontend display
            html_result = markdown.markdown(formatted_report, extensions=['tables', 'fenced_code'])

            # 10. Optionally save to database (保存到候选股表)
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
    """Get candidate analysis status for a specific stock"""
    status = candidate_analysis_status.get(symbol, {"status": "idle", "message": "", "result": ""})
    return status

# --- Strategy Management API ---

@app.get("/api/strategies")
async def list_strategies():
    """List all strategies"""
    return database.get_all_strategies()

@app.get("/api/strategies/{slug}")
async def get_strategy(slug: str):
    """Get strategy details including params"""
    strategy = database.get_strategy_by_slug(slug)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return strategy

class StrategyTemplateUpdate(BaseModel):
    template: str

@app.post("/api/strategies/{id}/template")
async def update_strategy_template(id: int, update: StrategyTemplateUpdate):
    """Update strategy prompt template"""
    success = database.update_strategy_template(id, update.template)
    if success:
        return {"status": "success", "message": "Updated template"}
    raise HTTPException(status_code=400, detail="Update failed")

class StrategyParamUpdate(BaseModel):
    key: str
    value: str

@app.post("/api/strategies/{id}/params")
async def update_strategy_param(id: int, param: StrategyParamUpdate):
    """Update strategy parameter"""
    success = database.update_strategy_param(id, param.key, param.value)
    if success:
        return {"status": "success", "message": f"Updated param {param.key}"}
    raise HTTPException(status_code=400, detail="Update failed")

if __name__ == "__main__":
    uvicorn.run("web_server:app", host="0.0.0.0", port=8100, reload=True, access_log=False)