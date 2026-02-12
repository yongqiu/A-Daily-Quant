from typing import Dict, Any, List
from datetime import datetime
import pandas as pd

def build_market_context(
    monitor_engine, 
    stock_symbol: str = None
) -> Dict[str, Any]:
    """
    通用市场上下文构建器
    
    统一获取：
    1. 大盘指数 (Market Index) - 上证指数
    2. 板块信息 (Sector Info) - 涨跌幅、排名
    3. 市场情绪 (Market Sentiment) - 连板数、涨跌家数比 (Advanced)
    4. 宏观状态 (Macro Status) - 牛熊线位置
    
    Args:
        monitor_engine: MonitorEngine 实例 (用于获取缓存的市场数据)
        stock_symbol: 目标股票代码 (用于查找所属板块)
        
    Returns:
        Dict[str, Any]: 标准化的 Market Context 结构
    """
    
    # Init context structure
    context = {
        "market_index": {
            "name": "上证指数",
            "price": 0.0,
            "change_pct": 0.0,
            "trend": "震荡",
            "status_desc": "未知"
        },
        "sector_info": {
            "name": "N/A",
            "change_pct": 0.0,
            "rank": "N/A"
        },
        "sentiment": {
            "limit_up_count": "N/A",
            "score": 50
        }
    }

    try:
        # 1. 获取基础指数数据 (Realtime)
        index_data = monitor_engine.get_market_index()
        context["market_index"]["price"] = index_data.get("price", 0)
        context["market_index"]["change_pct"] = index_data.get("change_pct", 0)

        # 2. 计算高级大盘状态 (Trend + Volume)
        # 使用 monitor_engine 的缓存获取历史
        if hasattr(monitor_engine, 'get_market_history_cached'):
            index_df = monitor_engine.get_market_history_cached()
            
            if index_df is not None and not index_df.empty:
                # Calculate MA5
                index_df['ma5'] = index_df['close'].rolling(5).mean()
                last_row = index_df.iloc[-1]
                
                current_price = index_data.get('price')
                if not current_price or current_price == 0:
                    current_price = last_row['close']
                    
                ma5_price = last_row['ma5']
                
                # Trend Logic
                trend = "震荡"
                if current_price > ma5_price * 1.005: 
                    trend = "上涨"
                elif current_price < ma5_price * 0.995: 
                    trend = "下跌"
                
                # Position
                pos_desc = "均线上方" if current_price > ma5_price else "均线下方"
                
                context["market_index"]["trend"] = trend
                context["market_index"]["status_desc"] = f"{trend} ({pos_desc})"
        
        # 3. 注入板块信息 (如果有股票代码)
        if stock_symbol:
            from data_fetcher import load_sector_map, get_sector_performance
            
            sector_map = load_sector_map()
            sector_name = sector_map.get(stock_symbol, 'N/A')
            context["sector_info"]["name"] = sector_name
            
            if sector_name and sector_name != 'N/A':
                 sector_change = get_sector_performance(sector_name)
                 context["sector_info"]["change_pct"] = sector_change
            
        # 4. 其它情绪指标 (Placeholder for now, or fetch from DB/API)
        # context["sentiment"]["limit_up_count"] = ...

    except Exception as e:
        print(f"⚠️ Market Context Build Error: {e}")
        
    print(f"🌍 Market Context Built: Index={context['market_index']['change_pct']}%, Sector={context['sector_info']['name']}")
    return context
