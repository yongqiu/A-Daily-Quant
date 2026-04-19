"""
Web Server for A-Share Strategy Monitor
A股策略监控系统 Web 服务器
为前端提供 API 并运行后台监控任务。
"""

from fastapi import FastAPI, Request, BackgroundTasks, HTTPException, Query
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
from typing import Any, Dict, Optional

# 清除代理环境以防止与 akshare 的连接问题
for env_var in [
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "http_proxy",
    "https_proxy",
    "ALL_PROXY",
    "all_proxy",
]:
    if env_var in os.environ:
        print(f"⚠️ Clearing proxy environment variable: {env_var}")
        os.environ.pop(env_var)

# 强制设置 no_proxy 以忽略任何系统级代理
os.environ["no_proxy"] = "*"

from monitor_engine import MonitorEngine
from data_fetcher import (
    fetch_data_dispatcher,
    calculate_start_date,
    fetch_stock_info,
    load_sector_map,
    get_sector_performance,
)
from indicator_calc import calculate_indicators, get_latest_metrics  # 评分 API 需要导入
from monitor_engine import get_realtime_data  # 评分 API 需要导入
from data_provider.base import DataFetcherManager  # 新的数据管理器
import database  # 添加数据库导入
from stock_screener import print_detailed_metrics  # 导入日志辅助函数
from data_fetcher_ts import fetch_stock_data_ts, fetch_daily_basic_ts
from data_fetcher_tx import get_stock_realtime_tx
from stock_scoring import get_score
from contextlib import asynccontextmanager
from analysis_snapshot import build_analysis_snapshot, build_snapshot_storage_view
from scoring_pipeline import attach_scores_to_snapshot

from llm_analyst import generate_analysis as base_generate_analysis
from strategy_data_factory import StrategyDataFactory


SCORE_SNAPSHOT_TTL_SECONDS = 15 * 60
score_snapshot_cache = {
    "date": datetime.now().strftime("%Y-%m-%d"),
    "items": {},
}


def _run_generate_analysis(**kwargs):
    """
    通过数据工厂拦截并统一装载 extra_indicators 后，再执行大模型生成
    """

    # 如果传入了 context 参数，从中提取 stock_info/realtime_data/tech_data
    ctx = kwargs.get("context", {})
    stock_info_for_extra = kwargs.get("stock_info") or ctx.get("stock_info", {})
    realtime_data_for_extra = kwargs.get("realtime_data") or ctx.get(
        "realtime_data", {}
    )
    tech_data_for_extra = kwargs.get("tech_data") or ctx.get("tech_data", {})

    extra = StrategyDataFactory.fetch_extra_indicators(
        stock_info=stock_info_for_extra,
        analysis_type=kwargs.get("analysis_type", "holding"),
        realtime_data=realtime_data_for_extra,
        tech_data=tech_data_for_extra,
    )
    kwargs["extra_indicators"] = extra
    result = base_generate_analysis(**kwargs)
    return result


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时运行初始检查与后台任务"""
    monitor_engine.refresh_targets()
    # 启动后台循环 (默认暂停状态)
    asyncio.create_task(market_data_loop())
    print("📋 监控系统已就绪，等待用户手动开启...")
    yield


app = FastAPI(title="A-Share Strategy Monitor", lifespan=lifespan)

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
    "is_monitoring": False,  # 监控开关 - 默认关闭，由用户手动开启
    "config": {
        "update_interval": 10  # 默认
    },
}


def _get_asset_type_from_symbol(symbol: str, fallback: str = "stock") -> str:
    if fallback and fallback != "stock":
        return fallback
    if symbol.startswith(("51", "56", "58", "159")):
        return "etf"
    return fallback or "stock"


def _reset_score_snapshot_cache_if_needed():
    today = datetime.now().strftime("%Y-%m-%d")
    if score_snapshot_cache["date"] != today:
        score_snapshot_cache["date"] = today
        score_snapshot_cache["items"].clear()


def _build_score_snapshot_cache_key(
    symbol: str,
    cost_price: float,
    asset_type: str,
    trade_date: Optional[str] = None,
) -> str:
    return "|".join(
        [
            trade_date or datetime.now().strftime("%Y-%m-%d"),
            symbol,
            asset_type or "stock",
            f"{float(cost_price or 0):.4f}",
        ]
    )


def _get_cached_score_snapshot(cache_key: str) -> Optional[Dict[str, Any]]:
    _reset_score_snapshot_cache_if_needed()
    cached = score_snapshot_cache["items"].get(cache_key)
    if not cached:
        return None

    age_seconds = (datetime.now() - cached["cached_at"]).total_seconds()
    if age_seconds > SCORE_SNAPSHOT_TTL_SECONDS:
        score_snapshot_cache["items"].pop(cache_key, None)
        return None

    return dict(cached["data"])


def _set_cached_score_snapshot(cache_key: str, data: Dict[str, Any]):
    _reset_score_snapshot_cache_if_needed()
    score_snapshot_cache["items"][cache_key] = {
        "cached_at": datetime.now(),
        "data": dict(data),
    }


def _merge_score_fields(target: Dict[str, Any], metrics: Optional[Dict[str, Any]]):
    if not metrics:
        return

    target["entry_score"] = metrics.get("entry_score")
    target["holding_score"] = metrics.get("holding_score")
    target["holding_state"] = metrics.get("holding_state")
    target["holding_state_label"] = metrics.get("holding_state_label")
    target["entry_score_details"] = metrics.get("entry_score_details", [])
    target["holding_score_details"] = metrics.get("holding_score_details", [])


def _get_or_compute_score_snapshot(
    symbol: str,
    cost_price: float,
    asset_type: str,
    trade_date: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    cache_key = _build_score_snapshot_cache_key(
        symbol=symbol,
        cost_price=cost_price,
        asset_type=asset_type,
        trade_date=trade_date,
    )
    cached = _get_cached_score_snapshot(cache_key)
    if cached:
        return cached

    metrics = get_score(
        symbol,
        cost_price=cost_price,
        asset_type=asset_type,
        include_news=False,
        trade_date=trade_date,
    )
    if metrics:
        _set_cached_score_snapshot(cache_key, metrics)
    return metrics


def _attach_dual_scores_to_items(items: list, price_key: str = "price") -> list:
    enriched = []
    for item in items:
        cloned = dict(item)
        symbol = cloned.get("symbol")
        if not symbol:
            enriched.append(cloned)
            continue

        try:
            if (
                cloned.get("entry_score") is not None
                or cloned.get("holding_score") is not None
            ):
                enriched.append(cloned)
                continue

            cost_price = float(cloned.get("cost_price") or 0)
            asset_type = _get_asset_type_from_symbol(
                symbol, cloned.get("asset_type") or cloned.get("type") or "stock"
            )
            metrics = _get_or_compute_score_snapshot(
                symbol=symbol,
                cost_price=cost_price,
                asset_type=asset_type,
            )
            _merge_score_fields(cloned, metrics)
        except Exception as e:
            print(f"⚠️ attach dual scores failed for {symbol}: {e}")

        enriched.append(cloned)
    return enriched


def _prefetch_daily_metrics_map(items: list, trade_date: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    symbols = [item.get("symbol") for item in items if item.get("symbol")]
    if not symbols:
        return {}

    return database.get_daily_metrics_batch(
        symbols, trade_date or datetime.now().strftime("%Y-%m-%d")
    )


def _attach_scores_from_metrics_map(items: list, metrics_map: Dict[str, Dict[str, Any]]) -> list:
    enriched = []
    for item in items:
        cloned = dict(item)
        _merge_score_fields(cloned, metrics_map.get(cloned.get("symbol")))
        enriched.append(cloned)
    return enriched


def _attach_scores_from_db_only(items: list, trade_date: Optional[str] = None) -> list:
    metrics_map = _prefetch_daily_metrics_map(
        items, trade_date=trade_date or datetime.now().strftime("%Y-%m-%d")
    )
    return _attach_scores_from_metrics_map(items, metrics_map)


def _sort_dashboard_items(items: list) -> list:
    return sorted(
        items,
        key=lambda item: (
            0 if item.get("type") == "holding" else 1,
            -float(item.get("holding_score") or -1),
            -float(item.get("entry_score") or -1),
            -float(item.get("change_pct") or 0),
        ),
    )


def _inject_star_state(stocks_list: list) -> list:
    """将数据库中的 is_starred 状态注入到实时 stocks 列表中。
    monitor_engine.run_check() 返回的数据不含 is_starred，
    每次直接覆盖会导致收藏状态丢失，必须从 DB 重新合并。
    """
    try:
        holdings = database.get_all_holdings()
        # 构建 { symbol -> is_starred } 映射
        star_map = {h["symbol"]: h.get("is_starred", False) for h in holdings}
        for stock in stocks_list:
            stock["is_starred"] = star_map.get(stock["symbol"], False)
    except Exception as e:
        print(f"⚠️ _inject_star_state 失败: {e}")
        # 尽量容错：如果 DB 失败，保留 stocks 原样
        for stock in stocks_list:
            stock.setdefault("is_starred", False)
    return stocks_list


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
            config = monitor_engine.load_config()  # 热重载配置
            interval = config.get("monitor", {}).get("update_interval_seconds", 10)
            market_state["config"]["update_interval"] = interval

            # 1. 更新指数
            # 检查 monitor_engine 是否有该方法，否则添加它
            if hasattr(monitor_engine, "load_config") is False:
                # 为了健壮性进行热补丁，以防文件顺序更改，
                # 但在本地 monitor_engine.load_config 作为全局函数存在
                # 我们需要调用模块级函数或将其设为静态
                from monitor_engine import load_config as _load_config

                monitor_engine.load_config = lambda: _load_config()

            index_data = monitor_engine.get_market_index()
            market_state["index"] = index_data

            # 2. 更新股票
            stocks_data = monitor_engine.run_check()
            stocks_data = _attach_scores_from_db_only(stocks_data)
            # 合并收藏状态（run_check 不含 is_starred）
            _inject_star_state(stocks_data)
            market_state["stocks"] = _sort_dashboard_items(stocks_data)

            market_state["last_update"] = datetime.now().strftime("%H:%M:%S")
            print(
                f"🔄 市场数据已于 {market_state['last_update']} 更新 (下次更新在 {interval}秒后)"
            )

            await asyncio.sleep(interval)

        except Exception as e:
            print(f"❌ 后台循环出错: {e}")
            await asyncio.sleep(10)  # Retry delay


# 检查是否使用 Vue 前端 (构建后的静态文件)
VUE_FRONTEND_PATH = Path(__file__).parent / "frontend" / "dist"
USE_VUE_FRONTEND = (
    VUE_FRONTEND_PATH.exists() and (VUE_FRONTEND_PATH / "index.html").exists()
)


@app.get("/api/status")
async def get_status():
    """前端轮询调用的 API"""
    # 如果监控未激活且股票列表为空，则从数据库加载
    if not market_state["is_monitoring"] and not market_state.get("stocks"):
        monitor_engine.refresh_targets()
        # 从数据库持仓中获取静态股票信息
        holdings = database.get_all_holdings()
        if holdings:
            base_items = [
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
                    "is_starred": h.get("is_starred", False),  # 收藏状态
                    "status": "等待监控开启",
                }
                for h in holdings
            ]
            market_state["stocks"] = _sort_dashboard_items(
                _attach_scores_from_db_only(base_items)
            )
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
            return {"status": "success", "data": stock_info}
        else:
            return {"status": "not_found", "message": f"未找到股票 {symbol} 的信息"}
    except Exception as e:
        print(f"❌ Error searching stock {symbol}: {e}")
        return {"status": "error", "message": f"搜索失败: {str(e)}"}


@app.get("/api/holdings")
async def get_holdings():
    """从数据库获取所有持仓及最新分析"""
    today = datetime.now().strftime("%Y-%m-%d")
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
        current_prices = {s["symbol"]: s for s in market_state.get("stocks", [])}

        new_stocks_list = []
        for h in holdings:
            existing = current_prices.get(h["symbol"])
            if existing:
                # 更新元数据但保留价格/状态
                existing["name"] = h["name"]
                existing["cost_price"] = h.get("cost_price", 0)
                existing["position_size"] = h.get("position_size", 0)
                existing["asset_type"] = h.get("asset_type", "stock")
                existing["is_starred"] = h.get("is_starred", False)  # 同步收藏状态
                new_stocks_list.append(existing)
            else:
                # 新股票
                new_stocks_list.append(
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
                        "is_starred": h.get("is_starred", False),  # 收藏状态
                        "status": "等待监控开启",
                    }
                )
        market_state["stocks"] = _sort_dashboard_items(
            _attach_scores_from_db_only(new_stocks_list)
        )
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
        holding.asset_type,
    )
    if success:
        monitor_engine.refresh_targets()
        refresh_market_state_from_db()
        return {"status": "success", "message": f"Added {holding.symbol}"}
    else:
        raise HTTPException(
            status_code=400, detail="Failed to add holding (already exists?)"
        )


@app.put("/api/holdings/{symbol}")
async def update_holding(symbol: str, holding: HoldingUpdate):
    """更新持仓详情"""
    success = database.update_holding(
        symbol, cost_price=holding.cost_price, position_size=holding.position_size
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


@app.patch("/api/holdings/{symbol}/star")
async def toggle_star(symbol: str):
    """切换持仓收藏状态"""
    new_state = database.toggle_star_holding(symbol)
    if new_state is None:
        raise HTTPException(status_code=404, detail="Holding not found or DB error")
    # 同步内存中对应条目的收藏状态
    for stock in market_state.get("stocks", []):
        if stock["symbol"] == symbol:
            stock["is_starred"] = new_state
            break
    return {"status": "success", "is_starred": new_state, "symbol": symbol}


@app.get("/api/selections")
async def get_selections(date: str = None):
    """从数据库获取每日精选"""
    print(f"📡 API /api/selections called with date='{date}' (Type: {type(date)})")

    # 如果未提供日期，数据库层处理最新数据的检索
    selections = database.get_daily_selections(date)
    selections = _attach_scores_from_db_only(
        selections, trade_date=date or datetime.now().strftime("%Y-%m-%d")
    )
    selections.sort(
        key=lambda item: (
            -float(item.get("entry_score") or -1),
            -float(item.get("volume_ratio") or 0),
        )
    )
    print(f"📦 Found {len(selections)} selections")

    # 获取可用日期
    try:
        conn = database.get_connection()
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT DISTINCT selection_date FROM daily_selections ORDER BY selection_date DESC LIMIT 30"
            )
            dates = []
            for row in cursor.fetchall():
                value = row.get("selection_date")
                if not value:
                    continue
                dates.append(
                    value.strftime("%Y-%m-%d")
                    if hasattr(value, "strftime")
                    else str(value)[:10]
                )
    except Exception as e:
        print(f"❌ Error getting available dates: {e}")
        dates = []

    return {"selections": selections, "available_dates": dates}


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
        stocks_data = _attach_scores_from_db_only(stocks_data)
        # 合并收藏状态再覆盖（run_check 不含 is_starred）
        _inject_star_state(stocks_data)
        market_state["stocks"] = _sort_dashboard_items(stocks_data)

        # 3. 更新时间戳
        market_state["last_update"] = datetime.now().strftime("%H:%M:%S")

        print(
            f"✅ 实时数据刷新完成: {len(stocks_data)} 只股票, 指数: {index_data['name']} {index_data['price']}"
        )

        return {
            "status": "success",
            "stocks": stocks_data,
            "index": index_data,
            "last_update": market_state["last_update"],
            "message": f"成功获取 {len(stocks_data)} 只股票实时数据",
        }
    except Exception as e:
        print(f"❌ 实时数据刷新失败: {e}")
        return {
            "status": "error",
            "message": f"数据获取失败: {str(e)}",
            "stocks": [],
            "index": market_state["index"],
        }


@app.get("/api/kline/{symbol}")
async def get_kline_data(symbol: str, period: str = "daily"):
    """
    获取图表的 K 线数据
    周期：日线、周线、月线 (daily, weekly, monthly)
    """
    # 1. 查找目标以了解其资产类型
    target = next((t for t in monitor_engine.targets if t["symbol"] == symbol), None)

    asset_type = "stock"  # 默认
    if target:
        asset_type = target.get("asset_type", "stock")

    # 2. 将原始 K 线 dataframe 转换为图表的列表格式
    # [Date, Open, Close, Low, High, Volume]

    try:
        # 根据周期确定天数
        days_map = {"daily": 365, "weekly": 365, "monthly": 730}
        days = days_map.get(period, 365)

        start_date = calculate_start_date(days)

        # 将周期传递给调度器
        # 使用 DataManager 获取每日股票/ETF 数据以确保稳定性
        if period == "daily" and asset_type in ["stock", "etf"]:
            try:
                # get_daily_data 返回 (df, source_name)
                df, _ = data_manager.get_daily_data(symbol, start_date=start_date)
            except Exception as e:
                print(
                    f"DataManager Fetch Failed: {e}, falling back to dispatcher"
                )
                df = fetch_data_dispatcher(
                    symbol, asset_type, start_date, period=period
                )
        else:
            df = fetch_data_dispatcher(symbol, asset_type, start_date, period=period)

        if df is None or df.empty:
            return {"status": "error", "message": "No data found"}

        # 计算 MA（简单移动平均线）
        # 使用滚动窗口
        df["ma5"] = df["close"].rolling(window=5).mean()
        df["ma10"] = df["close"].rolling(window=10).mean()
        df["ma20"] = df["close"].rolling(window=20).mean()
        df["ma30"] = df["close"].rolling(window=30).mean()

        # 将 NaN 填充为 None 以用于图表（ECharts 更好处理 '-' 或 null）
        # 使用对象类型安全地就地替换以允许 None
        df = df.astype(object)
        df = df.where(pd.notnull(df), None)

        dates = (
            df["date"]
            .apply(lambda x: x.strftime("%Y-%m-%d") if pd.notnull(x) else "")
            .tolist()
        )

        values = []
        volumes = []
        ma5 = []
        ma10 = []
        ma20 = []
        ma30 = []

        # Iteration
        for _, row in df.iterrows():
            values.append([row["open"], row["close"], row["low"], row["high"]])
            volumes.append(row["volume"])
            # 显式检查 None（NaN 已在上文中替换为 None）
            ma5.append(row["ma5"])
            ma10.append(row["ma10"])
            ma20.append(row["ma20"])
            ma30.append(row["ma30"])

        return {
            "status": "success",
            "symbol": symbol,
            "name": target["name"] if target else symbol,
            "period": period,
            "dates": dates,
            "values": values,
            "volumes": volumes,
            "ma5": ma5,
            "ma10": ma10,
            "ma20": ma20,
            "ma30": ma30,
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

    sections = {"market": "", "holdings": "", "candidates": ""}

    # 首先尝试读取各个部分
    found_sections = False
    for sec in sections.keys():
        path = os.path.join(report_dir, f"section_{sec}_{latest_date}.md")
        if os.path.exists(path):
            found_sections = True
            try:
                with open(path, "r", encoding="utf-8") as f:
                    sections[sec] = markdown.markdown(
                        f.read(), extensions=["tables", "fenced_code"]
                    )
            except:
                sections[sec] = "<p>读取失败</p>"

    if found_sections:
        return {
            "sections": sections,
            "filename": f"Report_{latest_date}",
            "mode": "sections",
        }

    # 回退到完整旧版文件
    full_path = os.path.join(report_dir, f"daily_strategy_full_{latest_date}.md")
    if os.path.exists(full_path):
        # ... 分割旧版文件的逻辑 ...
        try:
            with open(full_path, "r", encoding="utf-8") as f:
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
                    html_parts[k] = (
                        markdown.markdown(v, extensions=["tables", "fenced_code"])
                        if v.strip()
                        else ""
                    )

                return {
                    "sections": html_parts,
                    "filename": f"Full_{latest_date}",
                    "mode": "sections",
                }
        except:
            pass

    return {"content": "<h3>暂无数据</h3>", "filename": None}


# 报告状态和日志
report_generation_status = {"status": "idle", "message": ""}
report_logs = deque(maxlen=200)  # 存储最后 200 行日志


@app.post("/api/report/generate")
async def generate_report(background_tasks: BackgroundTasks, section: str = "all"):
    """触发每日报告生成脚本（可选部分）"""
    if report_generation_status["status"] == "running":
        return JSONResponse(status_code=400, content={"message": "生成任务已在运行中"})

    def _run_generation():
        report_generation_status["status"] = "running"
        report_generation_status["message"] = f"正在启动生成 ({section})..."
        report_logs.clear()  # 清除旧日志

        try:
            # 使用 Popen 作为子进程运行 main.py 以流式传输 stdout
            # 使用 sys.executable 确保我们使用相同的 python 解释器 (venv)
            cmd = [sys.executable, "-u", "main.py", "--section", section]

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            # 逐行读取 stdout
            for line in process.stdout:
                line = line.strip()
                if line:
                    print(f"[Report] {line}")  # 也打印到后端控制台
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
                report_generation_status["message"] = (
                    f"生成失败 (Code {process.returncode}) - 查看日志详情"
                )

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
realtime_analysis_status = {}  # {symbol: {"status": "idle"|"running"|"success"|"error", "message": "", "result": ""}}


@app.post("/api/analyze/{symbol}/score")
async def calculate_stock_score(
    symbol: str,
    trade_date: Optional[str] = Query(None),
):
    """
    阶段 1：仅计算指标和评分（无 AI 分析）。
    保存到 'daily_metrics' 表。
    数据源：Tushare Unified (stock_scoring.py)
    """
    print("🚀🚀🚀 /score calculate_stock_score (Unified Tushare Source)", symbol)
    try:
        # 1. 获取信息 (为了 Cost Price)
        holdings = database.get_all_holdings()
        stock_info = next((h for h in holdings if h["symbol"] == symbol), None)
        cost_price = float(stock_info.get("cost_price") or 0) if stock_info else 0.0

        # 自动检测类型 (如果不在持仓中，get_score 内部也有简单判断，但这里传递更好)
        # 如果 stock_info 存在，使用它的 asset_type，否则为 stock
        asset_type = stock_info.get("asset_type", "stock") if stock_info else "stock"

        # 2. 调用统一评分模块
        latest = get_score(
            symbol,
            cost_price=cost_price,
            asset_type=asset_type,
            include_news=True,
            trade_date=trade_date,
        )

        if not latest:
            return JSONResponse(
                status_code=500, content={"message": "评分计算失败（数据获取失败）"}
            )

        print(
            f"\n   --- DETAILED ANALYSIS: {latest.get('name', 'Unknown')} ({latest.get('symbol', '')}) ---"
        )
        print(f"   {latest}")
        _set_cached_score_snapshot(
            _build_score_snapshot_cache_key(
                symbol=symbol,
                cost_price=cost_price,
                asset_type=asset_type,
                trade_date=trade_date,
            ),
            latest,
        )

        # 3. 后处理：统一保存到 daily_metrics，确保详情面板只读取手动计算产物
        metric_date = trade_date or datetime.now().strftime("%Y-%m-%d")

        pattern_list = latest.get("pattern_details", [])
        latest["pattern_flags"] = ",".join(pattern_list) if pattern_list else ""

        success = database.save_daily_metrics(metric_date, latest)

        if success:
            return {
                "status": "success",
                "message": "指标计算完成，已存入数据库",
                "data": latest,
            }
        return JSONResponse(status_code=500, content={"message": "数据库保存失败"})

    except Exception as e:
        print(f"Calculate Score Error: {e}")
        import traceback

        traceback.print_exc()
        return JSONResponse(status_code=500, content={"message": f"计算失败: {str(e)}"})


@app.get("/api/analyze/{symbol}/metrics")
async def get_stock_metrics(
    symbol: str,
    date: str = None,
):
    """从数据库获取已保存的指标评分，不在详情面板打开时触发重算。"""
    today = datetime.now().strftime("%Y-%m-%d")
    if not date:
        date = today

    metrics = database.get_daily_metrics(symbol, date)
    if metrics:
        return {"status": "success", "data": metrics}

    return {"status": "not_found", "message": "No metrics found for this date"}


@app.get("/api/strategy/context-schema")
async def get_strategy_context_schema():
    """
    返回统一 Strategy Context 对象的 Schema (带中文注释)
    用于前端 Monaco Editor 或变量字典提供代码自动补全。
    """
    schema = [
        {
            "name": "ctx.stock.name",
            "type": "string",
            "desc": "股票名称，例如 '平安银行'",
        },
        {
            "name": "ctx.stock.symbol",
            "type": "string",
            "desc": "股票代码，例如 '000001'",
        },
        {
            "name": "ctx.stock.type",
            "type": "string",
            "desc": "资产类型，通常为 'stock' 或 'etf'",
        },
        {"name": "ctx.price", "type": "number", "desc": "当前有效价格（优先取实时价）"},
        {"name": "ctx.change_pct", "type": "number", "desc": "当前涨跌幅百分比 (%)"},
        {
            "name": "ctx.volume_ratio",
            "type": "number",
            "desc": "量比（实时成交量放大/缩小倍数）",
        },
        {"name": "ctx.indicators.ma5", "type": "number", "desc": "5日均线价格"},
        {
            "name": "ctx.indicators.ma20",
            "type": "number",
            "desc": "20日均线价格 (生命线)",
        },
        {
            "name": "ctx.indicators.ma60",
            "type": "number",
            "desc": "60日均线价格 (牛熊分界线)",
        },
        {"name": "ctx.indicators.rsi", "type": "number", "desc": "RSI (相对强弱指标)"},
        {
            "name": "ctx.indicators.atr_pct",
            "type": "number|string",
            "desc": "ATR 波动幅度百分比",
        },
        {
            "name": "ctx.indicators.resistance",
            "type": "number",
            "desc": "上方压力位 (Resistance)",
        },
        {
            "name": "ctx.indicators.support",
            "type": "number",
            "desc": "下方支撑位 (Support)",
        },
        {
            "name": "ctx.fundamental.pe_ratio",
            "type": "number|string",
            "desc": "市盈率 (PE动态)",
        },
        {
            "name": "ctx.fundamental.pb_ratio",
            "type": "number|string",
            "desc": "市净率 (PB)",
        },
        {
            "name": "ctx.fundamental.roe",
            "type": "number|string",
            "desc": "净资产收益率 (%)",
        },
        {"name": "ctx.fundamental.bvps", "type": "number|string", "desc": "每股净资产"},
        {"name": "ctx.fundamental.eps", "type": "number|string", "desc": "每股收益"},
        {
            "name": "ctx.fundamental.total_mv",
            "type": "number|string",
            "desc": "总市值（万）",
        },
        {
            "name": "ctx.computed.ma5_position",
            "type": "string",
            "desc": "股价相对于5日线位置，值='上方'或'下方'",
        },
        {
            "name": "ctx.computed.ma20_position",
            "type": "string",
            "desc": "股价相对于20日线位置，值='上方'或'下方'",
        },
        {
            "name": "ctx.computed.fund_status",
            "type": "string",
            "desc": "主力资金流向总结语句 (如: 主力净流入200万)",
        },
        {
            "name": "ctx.computed.winner_rate",
            "type": "string",
            "desc": "筹码获利盘状态总结 (如: 获利盘85% 筹码低位集中)",
        },
        {
            "name": "ctx.computed.strength",
            "type": "string",
            "desc": "核心技术形态优势总结",
        },
        {
            "name": "ctx.computed.pattern",
            "type": "string",
            "desc": "K线组合形态匹配解析",
        },
        {
            "name": "ctx.market.market_index.name",
            "type": "string",
            "desc": "大盘指数名称",
        },
        {
            "name": "ctx.market.market_index.price",
            "type": "number",
            "desc": "大盘指数当前点位",
        },
        {
            "name": "ctx.market.market_index.change_pct",
            "type": "number",
            "desc": "大盘指数单日涨跌幅 (%)",
        },
        {
            "name": "ctx.market.market_index.trend",
            "type": "string",
            "desc": "大盘短期趋势状态判定",
        },
        {
            "name": "ctx.market.sector_info.name",
            "type": "string",
            "desc": "当前股票所属主营板块名称",
        },
        {
            "name": "ctx.market.sector_info.change_pct",
            "type": "number",
            "desc": "所属板块整体涨跌幅 (%)",
        },
    ]
    return {"status": "success", "schema": schema}


@app.get("/api/analyze/{symbol}/report/stream")
async def analyze_stock_report_stream(
    symbol: str, mode: str = "multi_agent", agents: str = None
):
    """
    流式传输 AI 分析报告 (SSE)。
    模式：
    - multi_agent：全面辩论（技术派 vs 风险派 vs 基本面派 -> CIO）
    - single_prompt：使用单一稳健提示进行快速分析（旧版/快速）
    说明：
    - agents 参数可以按逗号分隔传递自定义参与辩论的专家slugs（如 ?agents=agent_trend_follower,agent_washout_hunter）。
    """

    async def _stream_generator():
        try:
            # 1. 统一工厂请求：一次性通过工厂拉取包含多级缓存的核心数据和高级策略上下文
            yield f"data: {json.dumps({'type': 'progress', 'value': 5, 'message': '🔍 通过统一数据工厂装载上下文...'})}\n\n"

            # 使用 StrategyDataFactory 准备所有原料
            context_payload = StrategyDataFactory.build_full_strategy_context(
                symbol=symbol,
                context_type="deep_candidate",
                monitor_engine=monitor_engine,
            )

            stock_info = context_payload.get("stock_info", {})
            tech_data = context_payload.get("tech_data", {})
            rt_data = context_payload.get("realtime_data", {})

            if not stock_info or not stock_info.get("symbol"):
                yield f"data: {json.dumps({'type': 'error', 'content': '找不到标的信息'})}\n\n"
                return

            # 载入 holdings (仅用于后续判断保存逻辑)
            holdings = database.get_all_holdings()
            today = datetime.now().strftime("%Y-%m-%d")
            monitor_engine_conf = monitor_engine.load_config()

            yield f"data: {json.dumps({'type': 'progress', 'value': 28, 'message': '💸 资金流向与核心模型加载中...'})}\n\n"

            yield f"data: {json.dumps({'type': 'step', 'content': '✅ 数据准备就绪，进入AI分析阶段'})}\n\n"

            # API 配置
            provider = monitor_engine_conf.get("api", {}).get("provider", "openai")
            api_config_key = f"api_{provider}"
            api_config = monitor_engine_conf.get(
                api_config_key, monitor_engine_conf.get("api")
            )

            if not api_config.get("api_key") and not api_config.get("credentials_path"):
                yield f"data: {json.dumps({'type': 'error', 'content': 'API Key 未配置'})}\n\n"
                return

            if mode == "multi_agent":
                from agent_analyst import MultiAgentSystem

                yield f"data: {json.dumps({'type': 'progress', 'value': 30, 'message': '🧠 正在组建专家辩论团队...'})}\n\n"

                agents_list = [a.strip() for a in agents.split(",")] if agents else None
                system = MultiAgentSystem(api_config, agents_slugs=agents_list)

                accumulated_html = ""
                # 传递 context_payload 包含所有变量，实现单一数据源贯穿
                async for event_json in system.run_debate_stream(
                    context=context_payload,
                    start_progress=35,
                ):
                    # 拦截最终结果以保存到数据库？
                    # 流直接生成 json 字符串
                    data = json.loads(event_json)
                    if data["type"] == "final_html":
                        accumulated_html = data["content"]
                        decision = data.get("decision", {})
                        agent_outputs = data.get("agent_outputs", [])
                        snapshot = context_payload.get("snapshot", {})
                        # Save to DB
                        try:
                            # 保存双评分分析对象
                            analysis_data = {
                                "price": rt_data.get("price", 0),
                                "ma20": tech_data.get("ma20", 0),
                                "trend_signal": tech_data.get(
                                    "ma_arrangement", "MultiAgent"
                                ),
                                "entry_score": tech_data.get("entry_score"),
                                "holding_score": tech_data.get("holding_score"),
                                "holding_state": tech_data.get("holding_state"),
                                "holding_state_label": tech_data.get("holding_state_label"),
                                "snapshot_version": snapshot.get("snapshot_version", 1),
                                "analysis_snapshot": build_snapshot_storage_view(snapshot),
                                "final_action": decision.get("final_action"),
                                "risk_level": decision.get("risk_level"),
                                "consensus_level": decision.get("consensus_level"),
                                "agent_outputs": agent_outputs,
                                "ai_analysis": accumulated_html,
                            }
                            # 确保价格有效
                            if (
                                analysis_data["price"] == 0
                                and tech_data.get("close")
                                and tech_data.get("close") > 0
                            ):
                                analysis_data["price"] = tech_data["close"]

                            today = datetime.now().strftime("%Y-%m-%d")

                            # 检查它是否实际上在持仓中以避免外键错误
                            is_holding = any(h["symbol"] == symbol for h in holdings)

                            if is_holding:
                                # 首先尝试严格保存为持仓分析
                                success = database.save_holding_analysis(
                                    symbol, today, analysis_data, mode=mode
                                )
                            else:
                                success = False

                            # 如果不是持仓或保存失败，尝试保存为精选更新
                            if not success:
                                # 我们假设它可能是一个正在被即时分析的候选者
                                # 检查今天是否存在于 daily_selections 中
                                current_selection = database.get_daily_selection(
                                    symbol, today
                                )
                                if current_selection:
                                    print(
                                        f"⚠️ {symbol} not in holdings, updating daily selection instead."
                                    )
                                    # Update selection with new AI analysis
                                    selection_update = {
                                        "symbol": symbol,
                                        "name": current_selection.get("name", ""),
                                        "close_price": analysis_data["price"],
                                        "volume_ratio": current_selection.get(
                                            "volume_ratio", 0
                                        ),
                                        "entry_score": analysis_data.get("entry_score"),
                                        "holding_score": analysis_data.get("holding_score"),
                                        "holding_state": analysis_data.get("holding_state"),
                                        "holding_state_label": analysis_data.get("holding_state_label"),
                                        "ai_analysis": accumulated_html,  # 存储 HTML 还是 Markdown？Agent 返回混合内容（Agents 返回 HTML，CIO 返回 MD）。
                                    }
                                    database.save_daily_selection(
                                        today, selection_update
                                    )

                        except Exception as e:
                            print(f"DB Save Error: {e}")

                    yield f"data: {event_json}\n\n"

            else:
                # 单agent策略生成
                # 为简单起见，我们只运行阻塞的单次生成并生成结果
                print(f"\n{'=' * 60}")
                print(f"{'=' * 60}")

                yield f"data: {json.dumps({'type': 'progress', 'value': 40, 'message': '⚡️ 单一专家模型快速分析中...'})}\n\n"
                yield f"data: {json.dumps({'type': 'step', 'content': '⏳ 连接 LLM 模型进行分析...'})}\n\n"

                # 我们可以重用现有的 generate_analysis，但它是阻塞的。
                # 理想情况下重写为异步，但现在先包装它。
                from llm_analyst import format_stock_section

                generate_analysis = _run_generate_analysis
                import markdown

                # 为了使其"流式"，我们伪造它或只是等待
                # 实际上 LLM 生成需要时间。

                # 在等待时伪造进度提升（因为阻塞）
                # 除非我们使用线程，否则无法在阻塞调用期间真正提升进度，但现在只需等待。

                try:
                    analysis = generate_analysis(
                        context=context_payload,
                        api_config=api_config,
                        analysis_type="deep_candidate",  # 盘后深度思考
                    )
                except Exception as gen_err:
                    print(
                        f"❌ [DEBUG stream/single_expert] generate_analysis 抛出异常: {gen_err}"
                    )
                    import traceback

                    traceback.print_exc()
                    yield f"data: {json.dumps({'type': 'error', 'content': f'LLM 分析异常: {str(gen_err)}'})}\n\n"
                    return

                yield f"data: {json.dumps({'type': 'progress', 'value': 90, 'message': '分析生成完毕，正在排版...'})}\n\n"

                # pre_daily_features 已由工厂注入 realtime_data 中
                pre_daily_features = rt_data.get("pre_daily_features", {})
                try:
                    formatted = format_stock_section(
                        stock_info, tech_data, analysis, pre_daily_features
                    )
                except Exception as fmt_err:
                    print(
                        f"❌ [DEBUG stream/single_expert] format_stock_section 异常: {fmt_err}"
                    )
                    import traceback

                    traceback.print_exc()
                    # 降级处理：直接使用原始 analysis
                    formatted = analysis

                html = markdown.markdown(formatted, extensions=["tables"])

                # Save
                analysis_data = {
                    "price": rt_data.get("price", 0),
                    "ma20": tech_data.get("ma20", 0),
                    "trend_signal": tech_data.get("ma_arrangement", ""),
                    "entry_score": tech_data.get("entry_score"),
                    "holding_score": tech_data.get("holding_score"),
                    "holding_state": tech_data.get("holding_state"),
                    "holding_state_label": tech_data.get("holding_state_label"),
                    "snapshot_version": context_payload.get("snapshot", {}).get("snapshot_version", 1),
                    "analysis_snapshot": build_snapshot_storage_view(context_payload.get("snapshot", {})),
                    "ai_analysis": formatted,
                }
                # Ensure price is valid
                if (
                    analysis_data["price"] == 0
                    and tech_data.get("close")
                    and tech_data.get("close") > 0
                ):
                    analysis_data["price"] = tech_data["close"]

                today = datetime.now().strftime("%Y-%m-%d")

                # 检查它是否实际上在持仓中以避免外键错误
                is_holding = any(h["symbol"] == symbol for h in holdings)

                if is_holding:
                    success = database.save_holding_analysis(
                        symbol, today, analysis_data, mode=mode
                    )
                else:
                    success = False

                if not success:
                    # 回退：如果不在持仓中，尝试保存到 daily_selections（候选模式）
                    try:
                        print(
                            f"⚠️ {symbol} not in holdings, attempting to save to daily_selections..."
                        )
                        # Try today first
                        current_sel = database.get_daily_selection(symbol, today)
                        target_date = today

                        # If not in today's list, try finding the latest entry (e.g. from yesterday)
                        if not current_sel:
                            current_sel = database.get_daily_selection(symbol, None)
                            if current_sel:
                                target_date = current_sel["selection_date"]

                        if current_sel:
                            sel_update = {
                                "symbol": symbol,
                                "name": current_sel.get(
                                    "name", stock_info.get("name", "")
                                ),
                                "close_price": analysis_data["price"],
                                "volume_ratio": current_sel.get("volume_ratio", 0),
                                "entry_score": analysis_data.get("entry_score"),
                                "holding_score": analysis_data.get("holding_score"),
                                "holding_state": analysis_data.get("holding_state"),
                                "holding_state_label": analysis_data.get("holding_state_label"),
                                "ai_analysis": formatted,
                            }
                            database.save_daily_selection(target_date, sel_update)
                            print(
                                f"✅ Saved candidate analysis (fallback) for {symbol} on {target_date}"
                            )
                        else:
                            print(
                                f"⚠️ {symbol} not found in any daily selections, analysis not saved to DB."
                            )
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
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
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

            realtime_step = (
                f"✅ 获取实时行情: ￥{rt_data['price']} ({rt_data['change_pct']}%)"
            )
            yield f"data: {json.dumps({'type': 'step', 'content': realtime_step})}\n\n"
            yield f"data: {json.dumps({'type': 'progress', 'value': 20, 'message': '📊 获取技术形态上下文...'})}\n\n"

            # 2. Get Context (Metrics)
            today = datetime.now().strftime("%Y-%m-%d")

            stock_info = {
                "symbol": symbol,
                "name": rt_data["name"],
                "asset_type": "stock",
            }

            # Context: Use latest metrics from DB or Recalc
            from indicator_calc import calculate_indicators, get_latest_metrics
            from data_fetcher import fetch_data_dispatcher, calculate_start_date

            db_metrics = database.get_daily_metrics(symbol, today)
            if not db_metrics:
                # Recalc
                start_date = calculate_start_date()
                df = fetch_data_dispatcher(symbol, "stock", start_date)
                if df is not None and not df.empty:
                    df = calculate_indicators(df)
                    tech_data = get_latest_metrics(df, 0)
                else:
                    tech_data = {}
            else:
                tech_data = db_metrics

            yield f"data: {json.dumps({'type': 'progress', 'value': 40, 'message': '🧠 正在进行AI盘中推演...'})}\n\n"

            # 3. Call LLM
            generate_analysis = _run_generate_analysis

            config = monitor_engine.load_config()
            provider = config.get("api", {}).get("provider", "openai")
            llm_config = config.get(f"api_{provider}", config.get("llm_api", {}))

            # context: Market & Sector
            # 1. Market Index (sh000001)
            print("🔍 [Intraday] 开始获取大盘指数数据...")
            try:
                index_data = get_stock_realtime_tx("sh000001")
                print(
                    f"🔍 [Intraday] get_stock_realtime_tx('sh000001') 返回: {index_data}"
                )

                if index_data:
                    market_index = {
                        "name": "大盘指数",
                        "price": index_data.get("price", 0),
                        "change_pct": index_data.get("change_pct", 0),
                        "trend": "未知",  # derive roughly from change
                    }
                    if market_index["change_pct"] > 0.5:
                        market_index["trend"] = "震荡向上"
                    elif market_index["change_pct"] < -0.5:
                        market_index["trend"] = "加速下跌"
                    else:
                        market_index["trend"] = "横盘震荡"

                    print(f"✅ [Intraday] 大盘指数构建完成: {market_index}")
                else:
                    print(
                        "⚠️ [Intraday] 无法获取上证指数实时数据 (get_stock_realtime_tx 返回 None)"
                    )
                    market_index = {
                        "name": "大盘指数",
                        "price": 0,
                        "change_pct": 0,
                        "trend": "未知",
                    }
            except Exception as e:
                print(f"❌ [Intraday] 获取上证指数数据异常: {e}")
                import traceback

                traceback.print_exc()
                market_index = {
                    "name": "大盘指数",
                    "price": 0,
                    "change_pct": 0,
                    "trend": "未知",
                }

            # 2. Sector
            # load_sector_map / get_sector_performance 已在文件顶部从 data_fetcher 导入
            sector_map = load_sector_map()
            sector_name = sector_map.get(symbol, "未知板块")

            sector_info = {"name": sector_name, "change_pct": 0, "rank": "N/A"}
            if sector_name != "未知板块":
                # Try to get sector performance
                # Note: get_sector_performance might be slow or need optimization,
                # for now we assume it returns a float or 0
                try:
                    sector_info["change_pct"] = get_sector_performance(sector_name)
                except:
                    pass

            market_context = {
                "market_index": market_index,
                "sector_info": sector_info,
                "sentiment": {
                    "limit_up_count": "N/A",  # Not available in realtime tx
                    "yesterday_limit_up": "N/A",
                },
            }
            print(f"🔍 [Intraday] market_context = {market_context}")

            context = {
                "stock_info": stock_info,
                "tech_data": tech_data,
                "realtime_data": rt_data,
                "market_context": market_context,
            }

            analysis = generate_analysis(
                context=context,
                api_config=llm_config,
                analysis_type="intraday",
            )

            # 4. Stream Result
            import markdown

            html = markdown.markdown(analysis)

            # 5. Save to Intraday Log
            try:
                save_intraday_log(
                    symbol=symbol,
                    price=rt_data.get("price", 0),
                    change_pct=rt_data.get("change_pct", 0),
                    analysis=analysis,
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
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/analyze/{symbol}/realtime")
async def analyze_stock_realtime(symbol: str, background_tasks: BackgroundTasks):
    """触发 AI 实时盘中分析"""
    if realtime_analysis_status.get(symbol, {}).get("status") == "running":
        return JSONResponse(
            status_code=400, content={"message": f"{symbol} 盘中分析正在运行中"}
        )

    def _run_realtime_analysis():
        realtime_analysis_status[symbol] = {
            "status": "running",
            "message": f"正在进行盘中诊断 {symbol}...",
            "result": "",
        }

        try:
            from data_fetcher import (
                fetch_data_dispatcher,
                calculate_start_date,
                fetch_stock_info,
            )
            from indicator_calc import calculate_indicators, get_latest_metrics

            generate_analysis = _run_generate_analysis
            from monitor_engine import get_realtime_data
            import markdown

            # 1. 获取股票信息
            # 首先尝试从持仓中获取，否则获取基本信息
            holdings = database.get_all_holdings()
            stock_info = next((h for h in holdings if h["symbol"] == symbol), None)

            if not stock_info:
                # 如果不在持仓中，获取基本信息
                basic_info = fetch_stock_info(symbol)
                if basic_info:
                    stock_info = {
                        "symbol": symbol,
                        "name": basic_info.get("name", symbol),
                        "asset_type": "stock",  # 如果需要，改进逻辑
                        "cost_price": None,
                    }
                else:
                    realtime_analysis_status[symbol] = {
                        "status": "error",
                        "message": f"无法获取 {symbol} 信息",
                        "result": "",
                    }
                    return

            # 2. 获取历史背景（需要 MA20、MA60 等技术锚点）
            start_date = calculate_start_date()
            asset_type = stock_info.get("asset_type", "stock")
            df = fetch_data_dispatcher(symbol, asset_type, start_date)

            latest_history = {}
            if df is not None and not df.empty:
                df = calculate_indicators(df)
                latest_history = get_latest_metrics(df, stock_info.get("cost_price", 0))

            # 3. Get Real-time Data (Crucial)
            # We also want Market Index status to pass to AI
            index_data = monitor_engine.get_market_index()

            realtime_dict = get_realtime_data([stock_info])
            realtime_data = realtime_dict.get(symbol)

            if not realtime_data:
                realtime_analysis_status[symbol] = {
                    "status": "error",
                    "message": "无法获取实时行情数据",
                    "result": "",
                }
                return

            # 将市场上下文注入 realtime_data 以供提示使用
            realtime_data["market_index_price"] = index_data.get("price", "N/A")
            realtime_data["market_index_change"] = index_data.get("change_pct", 0)

            # 4. 加载 LLM 配置
            config = monitor_engine.load_config()
            provider = config.get("api", {}).get("provider", "openai")
            llm_config = config.get(f"api_{provider}", config.get("llm_api", {}))

            if not llm_config.get("api_key"):
                realtime_analysis_status[symbol] = {
                    "status": "error",
                    "message": "LLM API Key missing",
                }
                return

            context = {
                "stock_info": stock_info,
                "tech_data": latest_history,
                "realtime_data": realtime_data,
            }
            # 5. 生成分析（模式：实时）
            analysis = generate_analysis(
                context=context,
                api_config=llm_config,
                analysis_type="realtime",
            )

            # 6. Result
            html_result = markdown.markdown(analysis, extensions=["tables"])

            realtime_analysis_status[symbol] = {
                "status": "success",
                "message": "诊断完成",
                "result": html_result,
                "raw": analysis,
                "timestamp": datetime.now().strftime("%H:%M:%S"),
            }

        except Exception as e:
            print(f"Realtime analysis error: {e}")
            realtime_analysis_status[symbol] = {
                "status": "error",
                "message": str(e),
                "result": "",
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
        return JSONResponse(
            status_code=400, content={"message": f"{symbol} 分析任务已在运行中"}
        )

    def _run_single_analysis():
        single_analysis_status[symbol] = {
            "status": "running",
            "message": f"正在分析 {symbol}...",
            "result": "",
        }

        try:
            generate_analysis = _run_generate_analysis
            import markdown

            holdings = database.get_all_holdings()
            stock_info = next((h for h in holdings if h["symbol"] == symbol), None)

            if not stock_info:
                single_analysis_status[symbol] = {
                    "status": "error",
                    "message": f"未找到股票 {symbol} 在持仓列表中",
                    "result": "",
                }
                return

            context_payload = StrategyDataFactory.build_full_strategy_context(
                symbol=symbol,
                context_type="holding",
                monitor_engine=monitor_engine,
            )
            stock_info = context_payload.get("stock_info", stock_info)
            latest = context_payload.get("tech_data", {})
            realtime_data = context_payload.get("realtime_data", {})
            snapshot = context_payload.get("snapshot", {})

            config = monitor_engine.load_config()
            provider = config.get("api", {}).get("provider", "openai")
            llm_config = config.get(f"api_{provider}", config.get("llm_api", {}))

            if not llm_config.get("api_key"):
                single_analysis_status[symbol] = {
                    "status": "error",
                    "message": f"LLM API 配置缺失 (Provider: {provider})",
                    "result": "",
                }
                return

            analysis = generate_analysis(
                context=context_payload,
                api_config=llm_config,
                analysis_type="holding",
            )

            from llm_analyst import format_stock_section

            formatted_report = format_stock_section(stock_info, latest, analysis)

            # 转换为 HTML 以供前端显示
            html_result = markdown.markdown(
                formatted_report, extensions=["tables", "fenced_code"]
            )

            # 10. 将分析保存到数据库（保存实时价格）
            analysis_data = {
                "price": latest.get("close", 0),  # 现在是实时价格
                "ma20": latest.get("ma20", 0),
                "trend_signal": latest.get("ma_arrangement", "未知"),
                "entry_score": latest.get("entry_score"),
                "holding_score": latest.get("holding_score"),
                "holding_state": latest.get("holding_state"),
                "holding_state_label": latest.get("holding_state_label"),
                "snapshot_version": snapshot.get("snapshot_version", 1),
                "analysis_snapshot": build_snapshot_storage_view(snapshot),
                "ai_analysis": formatted_report,  # 保存完整的 markdown 报告
            }

            analysis_date = datetime.now().strftime("%Y-%m-%d")

            try:
                database.save_holding_analysis(
                    symbol, analysis_date, analysis_data, mode="single_prompt"
                )
                print(f"✅ Analysis for {symbol} saved to database.")
            except Exception as db_e:
                print(f"⚠️ Failed to save analysis to DB: {db_e}")

            single_analysis_status[symbol] = {
                "status": "success",
                "message": f"{symbol} 分析完成",
                "result": html_result,
                "raw": formatted_report,
            }

        except Exception as e:
            single_analysis_status[symbol] = {
                "status": "error",
                "message": f"分析失败: {str(e)}",
                "result": "",
            }

    background_tasks.add_task(_run_single_analysis)
    return {"status": "started", "message": f"🤖 正在生成 {symbol} 的分析报告..."}


@app.get("/api/analyze/{symbol}/status")
async def get_single_analysis_status(symbol: str):
    """获取特定股票的分析状态"""
    status = single_analysis_status.get(
        symbol, {"status": "idle", "message": "", "result": ""}
    )
    return status


@app.get("/api/analyze/{symbol}/dates")
async def get_analysis_dates(symbol: str, mode: str = "multi_agent"):
    """获取股票的可用分析日期"""
    dates = database.get_analysis_dates_for_stock(symbol, mode=mode)
    return {"status": "success", "dates": dates}


@app.get("/api/analyze/{symbol}/history")
async def get_analysis_history(
    symbol: str, date: str = None, mode: str = "multi_agent"
):
    """获取特定日期的分析报告（如果没有日期,则获取最新的）"""
    try:
        import markdown

        # 特殊处理：如果是盘中分析模式，从 intraday_logs 表查询
        if mode == "intraday":
            try:
                from database import get_intraday_log

                # date 参数对于 intraday 是 analysis_time 的格式 (可选)
                intraday_result = get_intraday_log(symbol, analysis_time=date)

                if intraday_result:
                    # 将 markdown 转换为 HTML
                    html_result = markdown.markdown(
                        intraday_result["ai_content"],
                        extensions=["tables", "fenced_code"],
                    )

                    # 尝试获取股票名称
                    holdings = database.get_all_holdings()
                    stock_info = next(
                        (h for h in holdings if h["symbol"] == symbol), None
                    )
                    stock_name = stock_info["name"] if stock_info else symbol

                    return {
                        "status": "success",
                        "data": {
                            "symbol": symbol,
                            "name": stock_name,
                            "analysis_date": intraday_result[
                                "analysis_time"
                            ],  # 盘中分析使用 analysis_time
                            "price": intraday_result["price"],
                            "change_pct": intraday_result["change_pct"],
                            "ma20": 0,  # 盘中分析不存储 MA20
                            "trend_signal": "盘中",
                            "ai_analysis": intraday_result["ai_content"],
                            "html": html_result,
                            "mode": "intraday",
                        },
                    }
                else:
                    return {
                        "status": "no_data",
                        "message": f"暂无 {symbol} 的盘中分析记录",
                    }

            except Exception as intraday_error:
                print(f"❌ Error fetching intraday log for {symbol}: {intraday_error}")
                return {
                    "status": "error",
                    "message": f"查询盘中分析失败: {str(intraday_error)}",
                }

        # 获取持仓以查找股票信息
        holdings = database.get_all_holdings()
        stock_info = next((h for h in holdings if h["symbol"] == symbol), None)

        # 如果不在持仓中，它可能是一个候选选择
        if not stock_info:
            # 尝试在每日每日精选逻辑中查找（由用法暗示）或者如果能找到分析就继续
            pass

        # 首先尝试从 holding_analysis 表获取分析

        try:
            result = database.get_holding_analysis(
                symbol, analysis_date=date, mode=mode
            )

            if result:
                # 将 markdown 转换为 HTML
                html_result = markdown.markdown(
                    result["ai_analysis"], extensions=["tables", "fenced_code"]
                )

                name = stock_info["name"] if stock_info else result.get("name", symbol)

                return {
                    "status": "success",
                    "data": {
                        "symbol": symbol,
                        "name": name,
                        "analysis_date": result["analysis_date"],
                        "price": result["price"],
                        "ma20": result["ma20"],
                        "trend_signal": result["trend_signal"],
                        "entry_score": result.get("entry_score"),
                        "holding_score": result.get("holding_score"),
                        "holding_state": result.get("holding_state"),
                        "holding_state_label": result.get("holding_state_label"),
                        "snapshot_version": result.get("snapshot_version", 1),
                        "analysis_snapshot": result.get("analysis_snapshot"),
                        "final_action": result.get("final_action"),
                        "risk_level": result.get("risk_level"),
                        "consensus_level": result.get("consensus_level"),
                        "agent_outputs": result.get("agent_outputs", []),
                        "ai_analysis": result["ai_analysis"],
                        "html": html_result,
                        "mode": mode,
                    },
                }

            # 如果没有持仓分析，尝试回退到 daily_selections（用于选股器候选者）
            # 这对我们最初只有技术分析的新需求很重要
            # 我们将“候选”分析视为特殊回退

            selection = database.get_daily_selection(symbol, selection_date=date)
            if selection:
                # ai_analysis 可能已经是 HTML（如果来自多智能体）或 Markdown（如果来自候选分析）
                content = selection["ai_analysis"]
                is_html_likely = (
                    content.strip().startswith("<")
                    or "div" in content
                    or "span" in content
                )

                html_result = (
                    content
                    if is_html_likely
                    else markdown.markdown(
                        content, extensions=["tables", "fenced_code"]
                    )
                )

                return {
                    "status": "success",
                    "data": {
                        "symbol": symbol,
                        "name": selection["name"],
                        "analysis_date": selection["selection_date"],
                        "price": selection.get("close_price", 0),
                        "ma20": 0,  # 不直接存储在精选表中
                        "trend_signal": "Candidate",
                        "entry_score": selection.get("entry_score"),
                        "holding_score": selection.get("holding_score"),
                        "holding_state": selection.get("holding_state"),
                        "holding_state_label": selection.get("holding_state_label"),
                        "ai_analysis": content,
                        "html": html_result,
                        "mode": "candidate",
                    },
                }

            return {"status": "no_data", "message": f"暂无 {symbol} 的 {mode} 分析报告"}

        except Exception as db_error:
            print(f"❌ Database query error for {symbol}: {db_error}")
            return {"status": "error", "message": f"数据库查询失败: {str(db_error)}"}

    except Exception as e:
        print(f"❌ Error getting analysis for {symbol}: {e}")
        return {"status": "error", "message": f"获取失败: {str(e)}"}


@app.get("/api/analyze/{symbol}/latest")
async def get_latest_analysis(symbol: str, mode: str = "multi_agent"):
    """最新分析的旧端点"""
    return await get_analysis_history(symbol, date=None, mode=mode)


# --- 候选股票分析 ---

candidate_analysis_status = {}  # {symbol: {"status": "idle"|"running"|"success"|"error", "message": "", "result": ""}}


@app.post("/api/analyze/candidate/{symbol}")
async def analyze_candidate_stock(symbol: str, background_tasks: BackgroundTasks):
    """分析候选股票的买入机会（使用选股策略）"""
    if candidate_analysis_status.get(symbol, {}).get("status") == "running":
        return JSONResponse(
            status_code=400, content={"message": f"{symbol} 分析任务已在运行中"}
        )

    def _run_candidate_analysis():
        candidate_analysis_status[symbol] = {
            "status": "running",
            "message": f"正在分析 {symbol}...",
            "result": "",
        }

        try:
            generate_analysis = _run_generate_analysis
            import markdown
            from data_fetcher import fetch_stock_info

            stock_info_basic = fetch_stock_info(symbol)

            if not stock_info_basic:
                candidate_analysis_status[symbol] = {
                    "status": "error",
                    "message": f"无法找到股票 {symbol} 的信息",
                    "result": "",
                }
                return

            seed_stock_info = {
                "symbol": symbol,
                "name": stock_info_basic.get("name", symbol),
                "asset_type": "stock",  # 候选股默认为stock
                "cost_price": None,  # 候选股没有成本价
            }
            StrategyDataFactory._set_to_cache(symbol, "stock_info", seed_stock_info)

            context_payload = StrategyDataFactory.build_full_strategy_context(
                symbol=symbol,
                context_type="candidate",
                monitor_engine=monitor_engine,
            )
            stock_info = context_payload.get("stock_info", seed_stock_info)
            latest = context_payload.get("tech_data", {})
            realtime_data = context_payload.get("realtime_data", {})
            snapshot = context_payload.get("snapshot", {})

            if not latest:
                candidate_analysis_status[symbol] = {
                    "status": "error",
                    "message": f"无法获取 {symbol} 的统一分析快照",
                    "result": "",
                }
                return

            # --- 4.5 尝试从 daily_selections 恢复元数据 (排名，情绪等) ---
            from database import get_daily_selection

            # 尝试今天或最近
            selection_record = get_daily_selection(symbol, None)
            if selection_record and selection_record.get("ai_analysis"):
                import re
                import json

                # 检查隐藏的元数据
                # Format: <!-- METADATA: {"rank_in_sector": 5, ...} -->
                match = re.search(
                    r"<!-- METADATA: (.*?) -->", selection_record["ai_analysis"]
                )
                if match:
                    try:
                        meta_str = match.group(1)
                        metadata = json.loads(meta_str)
                        print(f"💡 Recovered metadata for {symbol}: {metadata.keys()}")

                        # 合并到最新指标
                        for k, v in metadata.items():
                            latest[k] = v
                            if realtime_data is not None and k not in realtime_data:
                                realtime_data[k] = v
                    except Exception as meta_e:
                        print(f"⚠️ Failed to parse metadata: {meta_e}")

            # --- 5.1 注入板块数据（修复候选提示中缺失的数据） ---
            try:
                sector_map = load_sector_map()
                sector_name = sector_map.get(symbol, "N/A")

                if realtime_data:
                    realtime_data["sector"] = sector_name
                    # 如果需要，也注入到最新数据中以保持一致性，但 Prompt 通常使用 realtime_data 来获取板块
                    latest["sector"] = sector_name

                    if sector_name != "N/A":
                        # 使用导入的 get_sector_performance
                        sector_change = get_sector_performance(sector_name)
                        realtime_data["sector_change"] = sector_change
                        latest["sector_change"] = sector_change
                    else:
                        realtime_data["sector_change"] = 0
                        latest["sector_change"] = 0

                    # 排名逻辑（目前占位，因为跳过了昂贵的计算）
                    realtime_data["rank_in_sector"] = "N/A"
                    latest["rank_in_sector"] = "N/A"
            except Exception as sec_e:
                print(f"⚠️ Sector fetch failed for {symbol}: {sec_e}")

            context_payload["realtime_data"] = realtime_data
            context_payload["tech_data"] = latest
            context_payload["snapshot"] = attach_scores_to_snapshot(
                build_analysis_snapshot(
                    stock_info=stock_info,
                    metrics=latest,
                    realtime_data=realtime_data,
                    market_context=context_payload.get("market_context", {}),
                    extra_indicators=context_payload.get("extra_indicators", {}),
                    intraday=context_payload.get("intraday", {}),
                )
            )

            # 6. Update latest with realtime price if available
            if realtime_data and realtime_data.get("price"):
                print(
                    f"📊 {symbol} - 历史收盘价: {latest.get('close')}, 实时价格: {realtime_data.get('price')}"
                )
                latest["close"] = round(realtime_data.get("price"), 3)
                latest["realtime_price"] = round(realtime_data.get("price"), 3)
                latest["change_pct_today"] = round(
                    realtime_data.get("change_pct", 0), 2
                )
                # Update date to today since we have realtime data
                latest["date"] = datetime.now().strftime("%Y-%m-%d")
            else:
                print(
                    f"⚠️ {symbol} - 无法获取实时价格，使用历史收盘价: {latest.get('close')}"
                )

            context_payload["snapshot"] = attach_scores_to_snapshot(
                build_analysis_snapshot(
                    stock_info=stock_info,
                    metrics=latest,
                    realtime_data=realtime_data,
                    market_context=context_payload.get("market_context", {}),
                    extra_indicators=context_payload.get("extra_indicators", {}),
                    intraday=context_payload.get("intraday", {}),
                )
            )

            # 7. Load LLM config
            config = monitor_engine.load_config()

            # Resolve API config dynamically based on provider
            provider = config.get("api", {}).get("provider", "openai")
            llm_config = config.get(f"api_{provider}", config.get("llm_api", {}))

            if not llm_config.get("api_key"):
                candidate_analysis_status[symbol] = {
                    "status": "error",
                    "message": f"LLM API 配置缺失 (Provider: {provider})",
                    "result": "",
                }
                return

            # 8. 生成 AI 分析（使用候选股策略 - analysis_type="candidate")
            analysis = generate_analysis(
                context=context_payload,
                api_config=llm_config,
                analysis_type="candidate",  # 🔥 使用选股策略
            )

            # 9. 格式化结果
            from llm_analyst import format_stock_section

            formatted_report = format_stock_section(stock_info, latest, analysis)

            # 转换为 HTML 以供前端显示
            html_result = markdown.markdown(
                formatted_report, extensions=["tables", "fenced_code"]
            )

            # 10. 可选地保存到数据库（保存到候选股表）
            try:
                selection_data = {
                    "symbol": stock_info["symbol"],
                    "name": stock_info["name"],
                    "close_price": latest["close"],
                    "volume_ratio": latest.get("volume_ratio", 0),
                    "entry_score": latest.get("entry_score"),
                    "holding_score": latest.get("holding_score"),
                    "holding_state": latest.get("holding_state"),
                    "holding_state_label": latest.get("holding_state_label"),
                    "ai_analysis": formatted_report,
                }
                analysis_date = datetime.now().strftime("%Y-%m-%d")
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
                    "name": stock_info["name"],
                    "price": latest["close"],
                    "score": latest.get("entry_score", 0),
                },
            }

        except Exception as e:
            candidate_analysis_status[symbol] = {
                "status": "error",
                "message": f"分析失败: {str(e)}",
                "result": "",
            }
            print(f"❌ Candidate analysis error for {symbol}: {e}")

    background_tasks.add_task(_run_candidate_analysis)
    return {"status": "started", "message": f"🤖 正在分析候选股 {symbol}..."}


@app.get("/api/analyze/candidate/{symbol}/status")
async def get_candidate_analysis_status(symbol: str):
    """获取特定股票的候选分析状态"""
    status = candidate_analysis_status.get(
        symbol, {"status": "idle", "message": "", "result": ""}
    )
    return status


# --- 策略管理 API ---


@app.get("/api/strategies")
async def list_strategies():
    """列出所有策略"""
    return database.get_all_strategies()


@app.get("/api/agents")
async def list_agents():
    """列出所有可用的多专家 Agent 选项"""
    strategies = database.get_all_strategies()
    # 过滤出适合作为专家 Agent 的策略
    agents = [
        s
        for s in strategies
        if s.get("category") in ("general", "multi_agent_expert")
        and not s.get("slug", "").startswith("agent_cio")
    ]
    return {"status": "success", "agents": agents}


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
    app.mount(
        "/assets",
        StaticFiles(directory=str(VUE_FRONTEND_PATH / "assets")),
        name="vue-assets",
    )
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
        return templates.TemplateResponse(
            "index.html", {"request": request, "title": "A-Share Monitor"}
        )

    @app.get("/strategies", response_class=HTMLResponse)
    async def strategy_config_page(request: Request):
        """渲染策略配置页面"""
        return templates.TemplateResponse(
            "strategies.html", {"request": request, "title": "策略配置中心"}
        )


if __name__ == "__main__":
    app_host = os.getenv("APP_HOST", "127.0.0.1")
    app_port = int(os.getenv("APP_PORT", "8100"))
    app_reload = os.getenv("APP_RELOAD", "true").lower() == "true"
    uvicorn.run(
        "web_server:app",
        host=app_host,
        port=app_port,
        reload=app_reload,
        access_log=False,
    )
