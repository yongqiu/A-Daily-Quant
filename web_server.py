"""
Web Server for A-Share Strategy Monitor
Exposes API for frontend and runs background monitoring tasks.
"""
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
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

from monitor_engine import MonitorEngine
from data_fetcher import fetch_data_dispatcher, calculate_start_date

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

@app.get("/api/status")
async def get_status():
    """API called by frontend poller"""
    # Return cached state immediately (non-blocking)
    return market_state

@app.post("/api/monitor/toggle")
async def toggle_monitor():
    """Toggle monitoring on/off"""
    market_state["is_monitoring"] = not market_state["is_monitoring"]
    status = "running" if market_state["is_monitoring"] else "paused"
    print(f"⏸️ Monitoring switched to: {status}")
    return {"status": status, "is_monitoring": market_state["is_monitoring"]}

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

if __name__ == "__main__":
    uvicorn.run("web_server:app", host="0.0.0.0", port=8100, reload=True, access_log=False)